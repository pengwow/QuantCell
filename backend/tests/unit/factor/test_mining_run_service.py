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
