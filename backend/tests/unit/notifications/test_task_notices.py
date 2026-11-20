"""任务终态通知 Hub 单测：影子表翻转 / 收件箱文案 / loop 调度三态"""

import asyncio
import threading
from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import common.notifications.inbox as inbox_mod
import common.notifications.task_notices as task_notices
import websocket.manager as ws_mod
from collector.db.database import Base, _import_all_models
from common.notifications.inbox import list_inbox_notifications
from common.notifications.inbox_models import AsyncTaskRecord, InboxNotification

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
    """Hub 与收件箱的落库统一走内存会话；顺手解绑主 loop，隔离调度行为"""
    task_notices.bind_event_loop(None)

    @contextmanager
    def fake(_ignored=None):
        yield db_session

    monkeypatch.setattr(task_notices, "use_db_session", fake)
    monkeypatch.setattr(inbox_mod, "use_db_session", fake)


class TestNotifyTaskEvent:
    def test_succeeded_writes_inbox_and_shadow(self, patched_sessions, db_session):
        task_notices.upsert_async_task_record("rl_train", "t-1", "queued", name="PPO运行")
        task_notices.notify_task_event("rl_train", "t-1", task_notices.TASK_STATUS_SUCCEEDED, name="PPO运行")

        item = list_inbox_notifications(limit=10, db_session=db_session)["items"][0]
        assert item["title"] == "RL训练任务已完成"
        assert item["level"] == "success"
        assert item["source"] == "rl_train"

        row = db_session.query(AsyncTaskRecord).filter_by(task_id="t-1").one()
        assert row.status == "succeeded"

    def test_failed_includes_error_text(self, patched_sessions, db_session):
        task_notices.notify_task_event(
            "factor_job",
            "f-9",
            task_notices.TASK_STATUS_FAILED,
            name="RS族计算",
            error="因子列缺失ecie\nTraceback(略)",
        )
        item = list_inbox_notifications(limit=10, db_session=db_session)["items"][0]
        assert item["level"] == "error"
        assert "RS族计算" in item["content"]
        assert "因子列缺失" in item["content"]
        row = db_session.query(AsyncTaskRecord).filter_by(task_id="f-9").one()
        assert row.status == "failed"

    def test_backtest_does_not_touch_shadow_table(self, patched_sessions, db_session):
        """影子表只服务 rl_train/factor_job；回测等域有自己的任务表"""
        task_notices.notify_task_event("backtest", "b-1", task_notices.TASK_STATUS_SUCCEEDED, name="BTC回测")
        item = list_inbox_notifications(limit=10, db_session=db_session)["items"][0]
        assert item["title"] == "回测任务已完成"
        assert db_session.query(AsyncTaskRecord).count() == 0

    def test_interrupted_level_and_shadow(self, patched_sessions, db_session):
        task_notices.upsert_async_task_record("factor_job", "f-1", "running", name="RS族计算")
        task_notices.notify_task_event("factor_job", "f-1", task_notices.TASK_STATUS_INTERRUPTED, name="RS族计算")
        item = list_inbox_notifications(limit=10, db_session=db_session)["items"][0]
        assert item["level"] == "warning"
        assert db_session.query(AsyncTaskRecord).filter_by(task_id="f-1").one().status == "interrupted"

    def test_invalid_status_raises(self, patched_sessions):
        with pytest.raises(ValueError):
            task_notices.notify_task_event("rl_train", "x", "RUNNING")

    def test_shadow_rows_not_duplicated(self, patched_sessions, db_session):
        task_notices.upsert_async_task_record("rl_train", "u-1", "queued")
        task_notices.upsert_async_task_record("rl_train", "u-1", "running")
        task_notices.notify_task_event("rl_train", "u-1", task_notices.TASK_STATUS_SUCCEEDED)
        assert db_session.query(AsyncTaskRecord).filter_by(task_id="u-1").count() == 1


class TestDispatch:
    """实时投递调度：无 loop 静默降级 / 绑定 loop 后经 WebSocketChannel 到 broadcast"""

    def test_no_loop_only_inbox(self, patched_sessions, db_session):
        """脚本/回测进程场景：无事件循环也不崩，只保留收件箱"""
        task_notices.bind_event_loop(None)
        task_notices.notify_task_event("rl_train", "n-1", task_notices.TASK_STATUS_SUCCEEDED, name="m")
        assert list_inbox_notifications(limit=10, db_session=db_session)["unread_count"] == 1

    @pytest.fixture()
    def worker_loop(self):
        loop = asyncio.new_event_loop()
        t = threading.Thread(target=loop.run_forever, daemon=True)
        t.start()
        yield loop
        loop.call_soon_threadsafe(loop.stop)
        t.join(timeout=3)
        loop.close()

    def test_dispatch_reaches_broadcast(self, patched_sessions, worker_loop, monkeypatch):
        task_notices.bind_event_loop(worker_loop)

        captured: list[dict] = []

        async def fake_broadcast(message, topic=None):
            captured.append(message)

        monkeypatch.setattr(ws_mod.manager, "broadcast", fake_broadcast)

        task_notices.notify_task_event("rl_train", "w-1", task_notices.TASK_STATUS_SUCCEEDED, name="m")

        # 等 worker loop 跑完投递协程（跨线程同步点）
        asyncio.run_coroutine_threadsafe(asyncio.sleep(0.3), worker_loop).result(timeout=5)

        assert len(captured) == 1
        payload = captured[0]
        assert payload["type"] == "notification"
        assert payload["data"]["metadata"]["task_type"] == "rl_train"
        assert payload["data"]["level"] == "success"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
