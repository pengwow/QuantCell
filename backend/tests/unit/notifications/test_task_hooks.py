"""RL / 因子任务埋点行为测试：影子表 upsert + 终态通知落收件箱。"""

from __future__ import annotations

import time
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import common.notifications.inbox as inbox_mod
import common.notifications.task_notices as task_notices
import services.rl_task_runner as rl_runner
from collector.db.database import Base, _import_all_models
from common.notifications.inbox import list_inbox_notifications
from common.notifications.inbox_models import AsyncTaskRecord, InboxNotification
from factor.job_manager import FactorJobManager

_import_all_models()


@pytest.fixture()
def db_session():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng, tables=[InboxNotification.__table__, AsyncTaskRecord.__table__])
    factory = sessionmaker(bind=eng, autoflush=False, expire_on_commit=False)
    session = factory()
    yield session
    session.close()


@pytest.fixture()
def patched_sessions(monkeypatch, db_session):
    """影子表与收件箱落库统一走内存会话；解绑主 loop 隔离调度行为"""
    task_notices.bind_event_loop(None)

    @contextmanager
    def fake(_ignored=None):
        yield db_session

    monkeypatch.setattr(task_notices, "use_db_session", fake)
    monkeypatch.setattr(inbox_mod, "use_db_session", fake)


def _wait_terminal(task_id: str, timeout: float = 10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        task = rl_runner.get_task(task_id)
        if task is not None and task.terminal:
            return task
        time.sleep(0.05)
    raise AssertionError(f"RL 任务 {task_id} 未在 {timeout}s 内进入终态")


def _shadow_rows(db):
    return {r.task_id: r.status for r in db.execute(select(AsyncTaskRecord)).scalars().all()}


class TestRlTaskHooks:
    def test_done_upserts_and_notifies(self, patched_sessions, db_session):
        rl_runner.reset_tasks()
        tid = rl_runner.submit_train_task({}, train_fn=lambda c, r: SimpleNamespace(model_path=None))
        task = _wait_terminal(tid)
        assert task.status == "done"

        rows = _shadow_rows(db_session)
        assert rows[tid] == "succeeded"
        items = list_inbox_notifications(limit=10, db_session=db_session)["items"]
        assert len(items) == 1
        assert items[0]["source"] == "rl_train"
        assert items[0]["title"] == "RL训练任务已完成"

    def test_running_upsert_seen_by_train_fn(self, patched_sessions, db_session):
        rl_runner.reset_tasks()
        seen = {}

        def fake_train(config, reporter):
            # 此刻主线程在轮询 sleep，session 无并发使用
            seen["rows"] = _shadow_rows(db_session)
            return SimpleNamespace(model_path=None)

        tid = rl_runner.submit_train_task({}, train_fn=fake_train)
        _wait_terminal(tid)
        # train_fn 运行时任务已翻 running：影子行应已同步翻转
        assert seen["rows"][tid] == "running"

    def test_error_maps_to_failed(self, patched_sessions, db_session):
        rl_runner.reset_tasks()

        def boom(config, reporter):
            raise RuntimeError("boom")

        tid = rl_runner.submit_train_task({}, train_fn=boom)
        task = _wait_terminal(tid)
        assert task.status == "error"

        assert _shadow_rows(db_session)[tid] == "failed"
        items = list_inbox_notifications(limit=10, db_session=db_session)["items"]
        assert items[0]["level"] == "error"
        assert "boom" in items[0]["content"]

    def test_cancelled_quiet_shadow_only(self, patched_sessions, db_session):
        """cancelled 用户自己发起：只落影子行，不发通知"""
        rl_runner.reset_tasks()
        task = rl_runner.TrainTask(task_id="rltrain_case_cancel")
        with rl_runner._registry_lock:
            rl_runner._tasks[task.task_id] = task
        rl_runner._finish(task, "cancelled", message="已取消")

        assert _shadow_rows(db_session)["rltrain_case_cancel"] == "cancelled"
        items = list_inbox_notifications(limit=10, db_session=db_session)["items"]
        assert items == []


class TestFactorJobHooks:
    def test_completed_maps_to_succeeded(self, patched_sessions, db_session):
        # daemon 后台线程（sweeper/lease）随进程退出，测试无需显式清理
        mgr = FactorJobManager(heartbeat_interval=999)
        job_id = mgr.submit("mining", {}, runner=lambda on_p, on_p2, on_ev: {"n": 1})
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            status = mgr.get_status(job_id)
            if status and status["status"] == "completed":
                break
            time.sleep(0.05)
        else:
            raise AssertionError("factor job 未完成")

        assert list(_shadow_rows(db_session).values()) == ["succeeded"]
        items = list_inbox_notifications(limit=10, db_session=db_session)["items"]
        assert items[0]["source"] == "factor_job"

    def test_failed_maps_to_failed(self, patched_sessions, db_session):
        mgr = FactorJobManager(heartbeat_interval=999)

        def boom(on_p, on_p2, on_ev):
            raise RuntimeError("挖掘失败")

        job_id = mgr.submit("mining", {}, runner=boom)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            status = mgr.get_status(job_id)
            if status and status["status"] == "failed":
                break
            time.sleep(0.05)
        else:
            raise AssertionError("factor job 未落失败终态")

        assert list(_shadow_rows(db_session).values()) == ["failed"]
        items = list_inbox_notifications(limit=10, db_session=db_session)["items"]
        assert items[0]["level"] == "error"
