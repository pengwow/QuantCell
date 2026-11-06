"""P2-④ 迁移单测：factor_mining_runs → 研究会话，验证产物、幂等与状态口径。"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import factor.models  # 注册 factor 表
import research.models  # 注册 research 表
from collector.db.database import Base
from factor.models import FactorMiningRun
from research.migrate_legacy import migrate_run
from research.models import ResearchSession, ResearchTrial


@pytest.fixture()
def db():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        eng,
        tables=[FactorMiningRun.__table__, ResearchSession.__table__, ResearchTrial.__table__],
    )
    session = sessionmaker(bind=eng)()
    yield session
    session.close()


def _run(status: str, job_id: str, candidates: list[dict] | None = None, error: str | None = None) -> FactorMiningRun:
    return FactorMiningRun(
        job_id=job_id,
        status=status,
        params_json=json.dumps({"symbols": ["BTC/USDT"], "interval": "1h"}),
        stats_json=json.dumps({"llm_calls": 3, "total_tokens": 450}) if status == "completed" else None,
        result_json=json.dumps({"candidates": candidates}) if candidates is not None else None,
        error=error,
    )


def _completed_candidates() -> list[dict]:
    return [
        {
            "status": "success",
            "candidate": 1,
            "hypothesis": "动量反转",
            "code": "def f(): pass",
            "code_hash": "abc",
            "metrics": {"ic_mean": 0.1, "ic_ir": 0.4},
            "usage": {"total_tokens": 200},
        },
        {
            "status": "failed",
            "candidate": 2,
            "hypothesis": "波动率因子",
            "error": "数据不足",
            "usage": {"total_tokens": 120},
        },
    ]


def test_migrates_completed_run_with_trials(db):
    row = _run("completed", "job-ok-1", _completed_candidates())
    db.add(row)
    db.commit()

    out = migrate_run(db, row, owner_id="u1")
    assert out["skipped"] is None and out["trials"] == 2

    session = db.query(ResearchSession).one()
    assert session.owner_id == "u1" and session.mode == "quick" and session.status == "completed"
    cfg = json.loads(session.config_json)
    assert cfg["migrated_job_id"] == "job-ok-1" and cfg["migrated_at"]
    assert (session.llm_calls, session.token_used) == (3, 450) and session.loop_done == 1

    trials = db.query(ResearchTrial).all()
    assert [t.candidate_idx for t in trials] == [1, 2]
    assert all(t.quick_run_id == row.id for t in trials)
    # quick 口径：status 按候选成败、decision 不自动判定
    assert [t.status for t in trials] == ["evaluated", "failed"]
    assert all(t.decision is None for t in trials)


def test_migrates_failed_run_without_trials(db):
    row = _run("failed", "job-fail-1", error="LLM 超时")
    db.add(row)
    db.commit()

    out = migrate_run(db, row, owner_id="u1")
    session = db.query(ResearchSession).one()
    assert session.status == "failed" and session.error == "LLM 超时"
    assert out["trials"] == 0


def test_skips_still_running(db):
    row = _run("running", "job-run-1")
    db.add(row)
    db.commit()
    assert migrate_run(db, row, owner_id="u1")["skipped"] == "still_running"


def test_idempotent_re_run(db):
    db.add(_run("completed", "job-ok-2", _completed_candidates()))
    db.commit()
    row = db.query(FactorMiningRun).one()

    first = migrate_run(db, row, owner_id="u1")
    assert db.query(ResearchSession).count() == 1 and db.query(ResearchTrial).count() == 2

    second = migrate_run(db, row, owner_id="u1")
    assert second["skipped"] == "already_migrated" and second["session_id"] == first["session_id"]
    # 重复执行不产生新数据
    assert db.query(ResearchSession).count() == 1 and db.query(ResearchTrial).count() == 2
