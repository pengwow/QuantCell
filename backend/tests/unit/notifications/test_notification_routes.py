"""通知路由层集成测试：inbox 过滤参数透传、单条已读、全部已读返回值

inbox 函数级语义由 test_inbox.py 守护；这里只验证 FastAPI 层的参数接线。
"""

from contextlib import contextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import utils.auth as auth_mod
from collector.db.database import Base, _import_all_models
from common.notifications import inbox
from common.notifications.inbox_models import AsyncTaskRecord, InboxNotification
from common.notifications.routes import router

_import_all_models()


@pytest.fixture()
def env(monkeypatch):
    """内存 SQLite + TestClient；路由内 use_db_session 替换为内存会话工厂"""
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng, tables=[InboxNotification.__table__, AsyncTaskRecord.__table__])
    factory = sessionmaker(bind=eng, autoflush=False, expire_on_commit=False)
    session = factory()

    # routes.py 的 is_guest_user 是路由函数体内的普通调用（非 Depends），
    # app.dependency_overrides 管不到它；走豁免开关短路（is_guest_user 首行判 is_auth_exempt）
    monkeypatch.setattr("utils.rbac.is_auth_exempt", lambda: True)

    @contextmanager
    def fake_use_db_session(_db_session=None):
        yield session

    orig = inbox.use_db_session
    inbox.use_db_session = fake_use_db_session
    try:
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[auth_mod.get_current_user] = lambda: {"user_id": 1}
        yield TestClient(app), session
    finally:
        inbox.use_db_session = orig
        session.close()


def _seed(session) -> None:
    assert inbox.record_inbox_notification(
        title="RL完成", content="x", level="success", source="rl_train", db_session=session
    )
    assert inbox.record_inbox_notification(title="系统", content="y", level="info", source="system", db_session=session)


class TestInboxRoutes:
    def test_task_type_filter(self, env):
        client, session = env
        _seed(session)
        resp = client.get("/api/v1/notifications/inbox", params={"task_type": "rl_train"})
        assert resp.status_code == 200
        items = resp.json()["data"]["items"]
        assert [it["title"] for it in items] == ["RL完成"]

    def test_unread_filter(self, env):
        client, session = env
        _seed(session)
        inbox.mark_inbox_read(db_session=session)
        _seed_new(session)
        resp = client.get("/api/v1/notifications/inbox", params={"unread": "true"})
        assert resp.status_code == 200
        assert [it["title"] for it in resp.json()["data"]["items"]] == ["again"]


def _seed_new(session) -> None:
    assert inbox.record_inbox_notification(
        title="again", content="z", level="info", source="system", db_session=session
    )


class TestSingleReadRoute:
    def test_read_then_404(self, env):
        client, session = env
        _seed(session)
        resp = client.get("/api/v1/notifications/inbox")
        first_id = resp.json()["data"]["items"][0]["id"]

        ok = client.post(f"/api/v1/notifications/inbox/{first_id}/read")
        assert ok.status_code == 200
        assert ok.json()["data"]["read"] is True

        missing = client.post("/api/v1/notifications/inbox/999/read")
        assert missing.status_code == 404

    def test_read_all_returns_marked(self, env):
        client, session = env
        _seed(session)
        resp = client.post("/api/v1/notifications/inbox/read-all")
        assert resp.status_code == 200
        assert resp.json()["data"]["marked"] == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
