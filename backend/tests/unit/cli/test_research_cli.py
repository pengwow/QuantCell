"""research CLI（migrate-mining-runs）测试。

cli.research 是单命令 typer 应用：调用时不带命令名（`--owner ...`），
与源码 docstring 的 `python -m cli.research --owner <id>` 一致。

DB 隔离：get_db_session 延迟导入 collector.db.database.SessionLocal，
这里把该模块的 SessionLocal / init_database_config 一起替换成 tmp sqlite，
不依赖 conftest 的测试库副本，也不会碰开发库。
"""

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from typer.testing import CliRunner

from cli.research import app
from factor.models import FactorMiningRun
from research.models import ResearchSession, ResearchTrial

CANDIDATE = {
    "candidate": 1,
    "status": "success",
    "hypothesis": "动量延续",
    "code": "factor = df['close'].pct_change(5)",
    "code_hash": "h1",
    "metrics": {"ic": 0.03},
    "usage": {"total_tokens": 50},
}


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    from collector.db import database

    # 测试会话里可能只 import 了部分模型模块（Worker 的 relationship('Strategy')
    # 找不到类就报错）；补齐并 configure mappers，与真实 init_database_config 一致
    database._import_all_models()
    engine = create_engine(f"sqlite:///{tmp_path / 'research_cli.db'}", connect_args={"check_same_thread": False})
    # 只建迁移涉及的三张表：Base.metadata 里还挂着别的模块（有未解析的外键），
    # 全量 create_all 会因无关模型报 NoReferencedTableError
    database.Base.metadata.create_all(
        engine,
        tables=[FactorMiningRun.__table__, ResearchSession.__table__, ResearchTrial.__table__],
    )
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(autocommit=False, autoflush=False, bind=engine))
    # get_db_session 每次调用都会 init_database_config；这里已手工建表并绑 bind，
    # 禁用初始化避免它把 SessionLocal 重新 configure 到 conftest 的库
    monkeypatch.setattr(database, "init_database_config", lambda: None)
    yield engine
    engine.dispose()


def _add_run(engine, job_id: str, status: str = "completed", candidates=None, stats=None, error=None) -> int:
    candidates = [CANDIDATE] if candidates is None else candidates
    payload = {
        "params_json": json.dumps({"loop_n": 1}, ensure_ascii=False),
        "stats_json": json.dumps(stats or {"llm_calls": 3, "total_tokens": 120}, ensure_ascii=False),
        "result_json": json.dumps({"candidates": candidates}, ensure_ascii=False),
    }
    with sessionmaker(bind=engine)() as db:
        run = FactorMiningRun(job_id=job_id, status=status, error=error, **payload)
        db.add(run)
        db.commit()
        db.refresh(run)
        return run.id


def _sessions(engine) -> list[dict]:
    with sessionmaker(bind=engine)() as db:
        return [
            {
                "id": row.id,
                "owner_id": row.owner_id,
                "mode": row.mode,
                "scenario": row.scenario,
                "status": row.status,
                "n_candidates": row.n_candidates,
                "config_json": row.config_json,
                "best_trial_id": row.best_trial_id,
                "loop_done": row.loop_done,
                "llm_calls": row.llm_calls,
                "token_used": row.token_used,
            }
            for row in db.query(ResearchSession).all()
        ]


def _trials(engine) -> list[dict]:
    with sessionmaker(bind=engine)() as db:
        return [
            {
                "session_id": row.session_id,
                "candidate_idx": row.candidate_idx,
                "status": row.status,
                "decision": row.decision,
                "quick_run_id": row.quick_run_id,
                "code_hash": row.code_hash,
                "metrics_json": row.metrics_json,
            }
            for row in db.query(ResearchTrial).all()
        ]


def test_dry_run_counts_without_writing(runner, isolated_db):
    """--dry-run 只打印将要迁移的 run，不写任何表。"""
    _add_run(isolated_db, "job-dry")
    result = runner.invoke(app, ["--owner", "u1", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "will migrate run=1 job=job-dry status=completed" in result.stdout
    assert "迁移 1，跳过 0，失败 0" in result.stdout
    assert _sessions(isolated_db) == []
    assert _trials(isolated_db) == []


def test_migrate_creates_quick_session(runner, isolated_db):
    """迁移成功：mode=quick 会话 + trial 落库，关键字段与返回契约正确。"""
    run_id = _add_run(isolated_db, "job-ok")
    result = runner.invoke(app, ["--owner", "u1"])
    assert result.exit_code == 0, result.output
    assert "migrate run=1 -> session=1 trials=1" in result.stdout
    assert "迁移 1，跳过 0，失败 0" in result.stdout

    sessions = _sessions(isolated_db)
    assert len(sessions) == 1
    session = sessions[0]
    assert session["owner_id"] == "u1"
    assert session["mode"] == "quick"
    assert session["scenario"] == "factor"
    assert session["status"] == "completed"
    assert session["n_candidates"] == 1
    assert session["llm_calls"] == 3
    assert session["token_used"] == 120
    assert session["loop_done"] == 1
    assert session["best_trial_id"] is None  # quick 不自动 promote

    config = json.loads(session["config_json"])
    assert config["migrated_job_id"] == "job-ok"
    assert "migrated_at" in config
    assert config["loop_n"] == 1  # 旧 params_json 原样带过来

    trials = _trials(isolated_db)
    assert len(trials) == 1
    trial = trials[0]
    assert trial["session_id"] == session["id"]
    assert trial["quick_run_id"] == run_id
    assert trial["candidate_idx"] == 1
    assert trial["status"] == "evaluated"
    assert trial["decision"] is None
    assert trial["code_hash"] == "h1"
    assert json.loads(trial["metrics_json"]) == {"ic": 0.03}


def test_migrate_is_idempotent(runner, isolated_db):
    """同一个 run 二跑被幂等锚点 skip，不产生第二个会话/trial。"""
    _add_run(isolated_db, "job-idem")
    assert runner.invoke(app, ["--owner", "u1"]).exit_code == 0

    second = runner.invoke(app, ["--owner", "u1"])
    assert second.exit_code == 0, second.output
    assert "already_migrated" in second.stdout
    assert "迁移 0，跳过 1，失败 0" in second.stdout
    assert len(_sessions(isolated_db)) == 1
    assert len(_trials(isolated_db)) == 1


def test_missing_owner_exits_nonzero(runner, isolated_db):
    """不传 --owner（只传其他参数，避免 no_args_is_help 走帮助分支）时 exit code 非 0。"""
    result = runner.invoke(app, ["--dry-run"])
    assert result.exit_code != 0
    assert "--owner" in result.output


def test_limit_caps_processed_runs(runner, isolated_db):
    """--limit 1 只迁移一条 run。"""
    _add_run(isolated_db, "job-a")
    _add_run(isolated_db, "job-b")
    result = runner.invoke(app, ["--owner", "u1", "--limit", "1"])
    assert result.exit_code == 0, result.output
    assert "迁移 1，跳过 0，失败 0" in result.stdout
    assert len(_sessions(isolated_db)) == 1
    assert len(_trials(isolated_db)) == 1
