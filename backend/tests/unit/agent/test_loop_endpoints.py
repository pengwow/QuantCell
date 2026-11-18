"""自迭代 Tab 两个只读端点：GET /agent/memory、GET /agent/loop-status。

直接调路由函数（与 test_daily_review 同口径）：工作区指到 tmp_path，
LAST_RUNS / MOUNTED_JOBS 用 core.scheduler 模块属性注入，lifecycle 状态目录
走 QUANTCELL_RL_LIFECYCLE_DIR 重定向——不碰真实 data 目录。
"""

import asyncio
import json

import pytest

from agent.api import routes
from core import scheduler

pytestmark = pytest.mark.unit


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """工作区指到 tmp（端点内再做 /memory 拼接）。"""
    monkeypatch.setattr(routes, "_AGENT_WORKSPACE", tmp_path)
    return tmp_path / "memory"


def test_memory_endpoint_empty_and_populated(workspace, monkeypatch):
    monkeypatch.delenv("QUANTCELL_AGENT_DREAM", raising=False)
    monkeypatch.setattr(scheduler, "LAST_RUNS", {})

    payload = asyncio.run(routes.get_agent_memory())
    assert payload["enabled"] is False
    assert payload["memory_markdown"] == ""
    assert payload["dream_cursor"] == 0
    assert payload["history_entries"] == 0
    assert payload["last_run"] is None

    workspace.mkdir(parents=True)
    (workspace / "MEMORY.md").write_text("# MEMORY.md\n- 事实\n", encoding="utf-8")
    (workspace / ".dream_cursor").write_text("5", encoding="utf-8")
    (workspace / "history.jsonl").write_text("\n".join(['{"cursor": 1}', '{"cursor": 2}']) + "\n", encoding="utf-8")
    monkeypatch.setenv("QUANTCELL_AGENT_DREAM", "1")
    last = {"ts_iso": "2026-11-18T04:00:00+00:00", "ok": True, "detail": "updated=True elapsed=7.8s"}
    monkeypatch.setattr(scheduler, "LAST_RUNS", {"agent_dream": last})

    payload = asyncio.run(routes.get_agent_memory())
    assert payload["enabled"] is True
    assert payload["memory_markdown"].startswith("# MEMORY.md")
    assert payload["dream_cursor"] == 5
    assert payload["history_entries"] == 2
    assert payload["last_run"] == last


def test_memory_endpoint_bad_cursor_is_zero(workspace):
    workspace.mkdir(parents=True)
    (workspace / ".dream_cursor").write_text("not-an-int", encoding="utf-8")
    assert asyncio.run(routes.get_agent_memory())["dream_cursor"] == 0


def test_loop_status_passes_through_mounted_and_last_run(monkeypatch, tmp_path):
    monkeypatch.setenv("QUANTCELL_RL_LIFECYCLE_DIR", str(tmp_path / "lifecycle"))
    monkeypatch.delenv("QUANTCELL_AUTO_RETRAIN", raising=False)
    monkeypatch.delenv("QUANTCELL_AUTO_PROMOTE", raising=False)
    last = {"ts_iso": "2026-11-18T03:30:00+00:00", "ok": False, "detail": ""}
    monkeypatch.setattr(scheduler, "MOUNTED_JOBS", {"rl_oos_gate_audit", "agent_dream"})
    monkeypatch.setattr(scheduler, "LAST_RUNS", {"rl_oos_gate_audit": last})

    payload = asyncio.run(routes.get_loop_status())
    jobs = {j["id"]: j for j in payload["jobs"]}
    assert jobs["rl_oos_gate_audit"]["mounted"] is True
    assert jobs["rl_oos_gate_audit"]["last_run"] == last
    assert jobs["rl_auto_retrain"]["mounted"] is False
    assert jobs["rl_auto_retrain"]["last_run"] is None
    assert payload["retrain"] == {"gates": {"auto_retrain": False, "auto_promote": False}, "families": []}


def test_loop_status_families_from_state(monkeypatch, tmp_path):
    lifecycle_dir = tmp_path / "lifecycle"
    lifecycle_dir.mkdir()
    (lifecycle_dir / "lifecycle_state.json").write_text(
        json.dumps(
            {
                "shadow": {"BTCUSDT": [{"date": "2026-11-17"}, {"date": "2026-11-18", "winner": "challenger"}]},
                "promotions": [{"family": "BTCUSDT", "status": "pending"}],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("QUANTCELL_RL_LIFECYCLE_DIR", str(lifecycle_dir))
    monkeypatch.setattr(scheduler, "MOUNTED_JOBS", set())
    monkeypatch.setattr(scheduler, "LAST_RUNS", {})

    families = asyncio.run(routes.get_loop_status())["retrain"]["families"]
    assert families == [
        {"family": "BTCUSDT", "status": "pending", "shadow_days": 2, "note": str({"winner": "challenger"})}
    ]


def test_record_run_and_dream_job_write_last_runs(monkeypatch):
    from agent.core import factory

    class _FakeDream:
        async def run(self) -> bool:
            return True

    class _FakeAgent:
        dream = _FakeDream()

    monkeypatch.setattr(scheduler, "LAST_RUNS", {})
    monkeypatch.setattr(factory, "get_agent", lambda: _FakeAgent())

    assert scheduler.run_agent_dream_job() is True
    run = scheduler.get_last_runs()["agent_dream"]
    assert run["ok"] is True
    assert run["detail"].startswith("updated=True elapsed=")
    assert run["ts_iso"]


def test_loop_status_corrupt_state_no_crash(monkeypatch, tmp_path):
    lifecycle_dir = tmp_path / "lifecycle"
    lifecycle_dir.mkdir()
    (lifecycle_dir / "lifecycle_state.json").write_text("{not json", encoding="utf-8")
    monkeypatch.setenv("QUANTCELL_RL_LIFECYCLE_DIR", str(lifecycle_dir))
    monkeypatch.setattr(scheduler, "MOUNTED_JOBS", set())
    monkeypatch.setattr(scheduler, "LAST_RUNS", {})

    assert asyncio.run(routes.get_loop_status())["retrain"]["families"] == []
