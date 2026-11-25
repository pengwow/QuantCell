"""BacktestJobManager 父进程职责单测（M1 Task 7/8 语义守护）。

只验证管理器自身的编排：投递字段、终态落库/通知映射、心跳超时、stop 的
success/forced 分支。真实进程池并发与 kill -9 见
tests/integration/backtest/test_backtest_job_pool.py。
"""

import os
import time

import pytest

from jobs import backtest_manager as bm
from jobs.spec import JobResult

TASK_ID = "task-1"


class _FakePool:
    def __init__(self) -> None:
        self.specs = []
        self.on_done = None

    def submit(self, spec, on_done) -> None:
        self.specs.append(spec)
        self.on_done = on_done


@pytest.fixture()
def manager(monkeypatch):
    mgr = bm.BacktestJobManager()
    pool = _FakePool()
    mgr._pool = pool
    marks: list[tuple] = []
    notices: list[tuple] = []
    rows: list[tuple] = []
    monkeypatch.setattr(mgr, "_mark_db", lambda tid, status, name, **kw: marks.append((tid, status, name, kw)))
    monkeypatch.setattr(mgr, "_update_db_row", lambda tid, status: rows.append((tid, status)))
    monkeypatch.setattr(
        mgr, "_notify", lambda tid, status, name, error=None: notices.append((tid, status, name, error))
    )
    mgr._test_pool = pool
    mgr._test_marks = marks
    mgr._test_notices = notices
    mgr._test_rows = rows
    yield mgr
    mgr._relay_stop.set()


def test_submit_builds_picklable_spec_and_marks_queued(manager):
    manager.submit(TASK_ID, "dual_ma", {"fast": 5}, {"symbols": ["BTC/USDT"], "interval": "1h"})

    spec = manager._test_pool.specs[0]
    assert spec.kind == "backtest" and spec.job_id == TASK_ID
    assert spec.payload == {
        "strategy_name": "dual_ma",
        "strategy_params": {"fast": 5},
        "backtest_config": {"symbols": ["BTC/USDT"], "interval": "1h"},
    }
    assert manager._test_marks[0][:2] == (TASK_ID, "queued")


def test_on_done_succeeded_maps_to_completed(manager):
    manager.submit(TASK_ID, "dual_ma", {}, {})

    manager._test_pool.on_done(TASK_ID, JobResult(status="succeeded", result_ref=TASK_ID))

    assert manager._test_marks[-1][:2] == (TASK_ID, "succeeded")
    assert manager._test_rows[-1] == (TASK_ID, "completed")
    assert manager._test_notices == [(TASK_ID, "completed", "dual_ma", None)]
    assert TASK_ID not in manager._jobs


def test_on_done_cancelled_maps_to_stopped_without_success_notice(manager):
    manager.submit(TASK_ID, "dual_ma", {}, {})

    manager._test_pool.on_done(TASK_ID, JobResult(status="cancelled"))

    assert manager._test_marks[-1][:2] == (TASK_ID, "cancelled")
    assert manager._test_rows[-1] == (TASK_ID, "stopped")
    # 管理器把 stopped 交给路由统一出口；notify_backtest_result 对 stopped 静默不发通知
    assert manager._test_notices == [(TASK_ID, "stopped", "dual_ma", None)]


def test_heartbeat_timeout_marks_interrupted(manager, monkeypatch):
    notified = []
    monkeypatch.setattr(bm, "notify_task_event", lambda *a, **kw: notified.append((a, kw)))
    monkeypatch.setattr(bm.progress_spool, "request_stop", lambda tid: None)
    manager.submit(TASK_ID, "dual_ma", {}, {})
    state = manager._jobs[TASK_ID]

    manager._mark_heartbeat_timeout(TASK_ID, state)

    assert state.finalized is True
    assert manager._test_marks[-1][1] == "interrupted"
    assert notified and notified[0][0][2] == bm.TASK_STATUS_INTERRUPTED
    # 已判超时后迟到的 on_done 不得再覆盖终态
    marks_before = len(manager._test_marks)
    manager._test_pool.on_done(TASK_ID, JobResult(status="failed", error="late"))
    assert len(manager._test_marks) == marks_before


def test_relay_marks_hung_worker_even_with_stale_snapshot(manager, monkeypatch):
    """快照文件仍在磁盘上时也必须判超时（曾因 elif 挂在 snapshot 分支永不触发）。"""
    manager.submit(TASK_ID, "dual_ma", {}, {})
    stale = {
        "pid": 4321,
        "ts": time.time() - bm.HEARTBEAT_TIMEOUT_SECONDS - 5,
        "progress": {"status": "running"},
    }
    monkeypatch.setattr(bm.progress_spool, "read_snapshot", lambda tid: stale)

    class _Tracker:
        def apply_snapshot(self, tid, progress):
            return None

    monkeypatch.setattr(bm, "get_progress_tracker", lambda: _Tracker())
    timed_out = []
    monkeypatch.setattr(manager, "_mark_heartbeat_timeout", lambda tid, state: timed_out.append(tid))

    deadline = time.time() + 5
    while not timed_out and time.time() < deadline:
        time.sleep(0.05)

    assert timed_out == [TASK_ID]


def test_stop_returns_none_for_unknown_task(manager):
    assert manager.stop("unknown") is None


def test_stop_success_when_worker_exits_in_time(manager):
    manager.submit(TASK_ID, "dual_ma", {}, {})
    manager._jobs[TASK_ID].done.set()
    manager._service.request_stop = lambda tid: {"status": "success"}  # type: ignore[method-assign]

    assert manager.stop(TASK_ID, confirm_timeout=0.1)["status"] == "success"


def test_stop_forced_kills_snapshot_pid(manager, monkeypatch):
    manager.submit(TASK_ID, "dual_ma", {}, {})
    manager._service.request_stop = lambda tid: {"status": "success"}  # type: ignore[method-assign]
    monkeypatch.setattr(bm.progress_spool, "request_stop", lambda tid: None)
    monkeypatch.setattr(bm.progress_spool, "read_snapshot", lambda tid: {"pid": 4321})
    killed = []
    monkeypatch.setattr(os, "kill", lambda pid, sig: killed.append((pid, sig)))

    result = manager.stop(TASK_ID, confirm_timeout=0.05)

    assert result["status"] == "forced"
    assert killed == [(4321, bm.signal.SIGKILL)]
    assert manager._jobs[TASK_ID].finalized is True
