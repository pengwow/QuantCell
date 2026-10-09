"""MiningRunService：建行、终态落库、懒修正、删除约束。"""

import json

import pytest

from factor.job_manager import JobStatus
from factor.mining_run_service import (
    COMPLETED,
    INTERRUPTED,
    RUNNING,
    MiningRunError,
    MiningRunService,
)
from factor.models import FactorMiningRun


@pytest.fixture
def svc():
    return MiningRunService()


PARAMS = {"instruments": ["BTCUSDT"], "interval": "1h", "n_rounds": 2, "n_candidates": 4}
RESULT = {
    "candidates": [],
    "best": [],
    "composite": None,
    "stats": {
        "generated": 3,
        "unique": 2,
        "succeeded": 1,
        "failed": 2,
        "redundant": 0,
        "rounds": 1,
        "symbols": ["BTCUSDT"],
        "interval": "1h",
        "model_name": "m",
    },
}


def test_create_running(db_session, svc):
    row = svc.create_running(db_session, "job-1", PARAMS)
    assert row.status == "running"
    assert json.loads(row.params_json)["interval"] == "1h"


def test_mark_completed_persists_result_and_stats(db_session, svc):
    svc.create_running(db_session, "job-1", PARAMS)
    svc.mark_completed(db_session, "job-1", RESULT)
    row = db_session.query(FactorMiningRun).filter_by(job_id="job-1").one()
    assert row.status == "completed" and row.finished_at is not None
    assert json.loads(row.result_json)["stats"]["succeeded"] == 1
    assert json.loads(row.stats_json)["generated"] == 3


def test_mark_failed_persists_error(db_session, svc):
    svc.create_running(db_session, "job-1", PARAMS)
    svc.mark_failed(db_session, "job-1", "boom")
    row = db_session.query(FactorMiningRun).filter_by(job_id="job-1").one()
    assert row.status == "failed" and row.error == "boom" and row.finished_at is not None


class _StubJob:
    def __init__(self, status, result=None, error=None):
        self.status = status
        self.result = result
        self.error = error


class _StubJobManager:
    def __init__(self, jobs):
        self._jobs = jobs

    def get(self, job_id):
        return self._jobs.get(job_id)


def test_reconcile_marks_interrupted_when_memory_gone(db_session, svc, monkeypatch):
    svc.create_running(db_session, "job-lost", PARAMS)
    monkeypatch.setattr("factor.mining_run_service.job_manager", _StubJobManager({}))
    _, runs = svc.list_runs(db_session)
    assert runs[0].status == INTERRUPTED and runs[0].finished_at is not None


def test_reconcile_backfills_completed_from_memory(db_session, svc, monkeypatch):
    # 终态回调落库失败的悬挂场景：内存已 completed 而 DB 仍 running → 补写
    svc.create_running(db_session, "job-1", PARAMS)
    monkeypatch.setattr(
        "factor.mining_run_service.job_manager",
        _StubJobManager({"job-1": _StubJob(JobStatus.COMPLETED, result=RESULT)}),
    )
    _, runs = svc.list_runs(db_session)
    assert runs[0].status == COMPLETED
    assert json.loads(runs[0].result_json)["stats"]["succeeded"] == 1


def test_running_stays_when_memory_running(db_session, svc, monkeypatch):
    svc.create_running(db_session, "job-1", PARAMS)
    monkeypatch.setattr(
        "factor.mining_run_service.job_manager",
        _StubJobManager({"job-1": _StubJob(JobStatus.RUNNING)}),
    )
    _, runs = svc.list_runs(db_session)
    assert runs[0].status == RUNNING


def test_get_run_not_found(db_session, svc):
    with pytest.raises(MiningRunError) as e:
        svc.get_run(db_session, 9999)
    assert e.value.kind == "not_found"


def test_delete_running_conflict_and_terminal_ok(db_session, svc):
    row = svc.create_running(db_session, "job-1", PARAMS)
    with pytest.raises(MiningRunError) as e:
        svc.delete_run(db_session, row.id)
    assert e.value.kind == "conflict"

    svc.mark_failed(db_session, "job-1", "x")
    svc.delete_run(db_session, row.id)
    assert db_session.query(FactorMiningRun).filter_by(id=row.id).count() == 0


def test_run_summary_and_detail_shapes(db_session, svc):
    from factor.mining_run_service import run_detail, run_summary

    row = svc.create_running(db_session, "job-1", PARAMS)
    s = run_summary(row)
    assert s["id"] == row.id and "result" not in s and s["stats"] is None
    assert s["params"]["instruments"] == ["BTCUSDT"]

    svc.mark_completed(db_session, "job-1", RESULT)
    d = run_detail(db_session.query(FactorMiningRun).filter_by(job_id="job-1").one())
    assert d["result"]["stats"]["failed"] == 2
    assert d["stats"]["generated"] == 3


def test_append_events_accumulates_and_caps(db_session, svc):
    from factor.mining_run_service import run_detail

    row = svc.create_running(db_session, "job-e1", {"instruments": ["BTCUSDT"]})

    svc.append_events(db_session, "job-e1", [{"idx": 0, "msg": "a"}, {"idx": 1, "msg": "b"}])
    svc.append_events(db_session, "job-e1", [{"idx": 2, "msg": "c"}])
    stored = json.loads(svc.get_run(db_session, row.id).events_json)
    assert [e["msg"] for e in stored] == ["a", "b", "c"]
    # 详情接口带出过程事件
    assert [e["msg"] for e in run_detail(svc.get_run(db_session, row.id))["events"]] == [
        "a",
        "b",
        "c",
    ]

    # 超过 500 截断，保留最新 500 条
    svc.append_events(db_session, "job-e1", [{"idx": i, "msg": f"x{i}"} for i in range(3, 505)])
    stored2 = json.loads(svc.get_run(db_session, row.id).events_json)
    assert len(stored2) == 500
    assert stored2[0]["msg"] == "x5"
    assert stored2[-1]["msg"] == "x504"


def test_ensure_events_column_idempotent_on_old_sqlite():
    # 模拟旧库（表无 events_json）→ ensure 补列后可追加；重复调用幂等
    from sqlalchemy import create_engine, inspect, text
    from sqlalchemy.orm import sessionmaker

    from factor.mining_run_service import MiningRunService

    eng = create_engine("sqlite:///:memory:")
    with eng.begin() as conn:
        # 升级前的表结构：与现模型一致，仅缺 events_json 列
        conn.execute(
            text(
                "CREATE TABLE factor_mining_runs (id INTEGER PRIMARY KEY, job_id VARCHAR(64), "
                "status VARCHAR(16), params_json TEXT, stats_json TEXT, result_json TEXT, "
                "error TEXT, created_at DATETIME, finished_at DATETIME)"
            )
        )

    service = MiningRunService()
    service.ensure_events_column(eng)
    cols = inspect(eng).get_columns("factor_mining_runs")
    assert "events_json" in {c["name"] for c in cols}
    # 再调一次不报错（幂等）
    service.ensure_events_column(eng)

    # 补列后旧表可正常追加事件
    sess = sessionmaker(bind=eng)()
    sess.execute(
        text("INSERT INTO factor_mining_runs (id, job_id, status, params_json) VALUES (1, 'job-old', 'running', '{}')")
    )
    sess.commit()
    service.append_events(sess, "job-old", [{"idx": 0, "msg": "旧库首条"}])
    raw = sess.execute(text("SELECT events_json FROM factor_mining_runs WHERE id = 1")).one()
    assert json.loads(raw[0]) == [{"idx": 0, "msg": "旧库首条"}]
