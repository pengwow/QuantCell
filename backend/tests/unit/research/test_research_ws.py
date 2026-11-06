"""研究事件 WS 发布桥与端点单测（PRD §8 #12）。

覆盖：跨线程投递、owner 隔离、无 loop/队列满的静默丢弃、append_event 挂钩、
端点认证拒绝与端到端推送。
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from collector.db.database import Base
from research import service
from research import ws as research_ws
from research.models import ResearchEvent, ResearchKnowledge, ResearchSession, ResearchTrial
from research.routes import research_ws_endpoint


@pytest.fixture(autouse=True)
def _reset_bridge():
    """发布桥是模块级单例（loop + subscribers），用例之间清场避免串扰。"""
    research_ws.set_event_loop(None)
    research_ws._subscribers.clear()
    yield
    research_ws.set_event_loop(None)
    research_ws._subscribers.clear()


@pytest.fixture()
def research_db():
    from contextlib import contextmanager

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        eng,
        tables=[
            ResearchSession.__table__,
            ResearchTrial.__table__,
            ResearchKnowledge.__table__,
            ResearchEvent.__table__,
        ],
    )
    Session = sessionmaker(bind=eng)
    db = Session()

    @contextmanager
    def factory():
        yield db

    try:
        yield db, factory
    finally:
        db.close()


def test_publish_reaches_subscribed_owner():
    """外部线程（此处模拟从当前线程非运行中的 loop）发布能投递到 owner 队列。"""
    q = research_ws.subscribe("u1")
    loop = asyncio.new_event_loop()
    research_ws.set_event_loop(loop)
    try:
        payload = {"session_id": 1, "event": {"stage": "loop.round", "msg": "hi"}}
        research_ws.publish_event("u1", payload)
        got = loop.run_until_complete(asyncio.wait_for(q.get(), 2))
        assert got == payload
    finally:
        loop.close()


def test_publish_owner_isolation():
    """owner 之间互不串扰：u1 的事件不会进 u2 的队列。"""
    q_other = research_ws.subscribe("u2")
    loop = asyncio.new_event_loop()
    research_ws.set_event_loop(loop)
    try:
        research_ws.publish_event("u1", {"x": 1})
        with pytest.raises(asyncio.TimeoutError):
            loop.run_until_complete(asyncio.wait_for(q_other.get(), 0.3))
    finally:
        loop.close()


def test_publish_without_loop_is_silent():
    """未绑定 loop（服务未启动/测试环境）发布不抛错、无副作用。"""
    research_ws.publish_event("u1", {"x": 1})


def test_publish_after_loop_closed_is_silent():
    loop = asyncio.new_event_loop()
    research_ws.set_event_loop(loop)
    loop.close()
    research_ws.publish_event("u1", {"x": 1})


def test_queue_full_drops_new_event():
    """积压满 200 条后丢新事件（旧事件保留，前端轮询补齐），不阻塞发布方。"""
    q = research_ws.subscribe("u1")
    loop = asyncio.new_event_loop()
    research_ws.set_event_loop(loop)
    try:
        for i in range(research_ws._QUEUE_MAX):
            q.put_nowait({"i": i})
        research_ws.publish_event("u1", {"drop": True})
        loop.run_until_complete(asyncio.sleep(0))
        assert q.qsize() == research_ws._QUEUE_MAX
        first = loop.run_until_complete(asyncio.wait_for(q.get(), 1))
        assert first == {"i": 0}  # 最旧的还在
    finally:
        loop.close()


def test_unsubscribe_removes_queue():
    q = research_ws.subscribe("u1")
    research_ws.unsubscribe("u1", q)
    # 重复 unsubscribe 幂等
    research_ws.unsubscribe("u1", q)
    assert "u1" not in research_ws._subscribers


def test_append_event_publishes_to_bridge(research_db):
    """append_event 落库后把事件推给会话 owner（端到端服务层钩子）。"""
    db, _ = research_db
    row = service.create_session(
        db, owner_id="u1", name="ws-test", mode="quick", scenario="factor", config={}, n_candidates=1
    )
    q = research_ws.subscribe("u1")
    loop = asyncio.new_event_loop()
    research_ws.set_event_loop(loop)
    try:
        event = service.append_event(db, row.id, "info", "test.stage", "hello ws")
        payload = loop.run_until_complete(asyncio.wait_for(q.get(), 2))
        assert payload["session_id"] == row.id
        assert payload["event"] == {
            "seq": event.id,
            "level": "info",
            "stage": "test.stage",
            "msg": "hello ws",
            "ts": int(event.ts or 0),
        }
    finally:
        loop.close()


def _make_client() -> TestClient:
    app = FastAPI()
    app.websocket("/ws/research")(research_ws_endpoint)
    return TestClient(app)


def test_ws_endpoint_rejects_unauthorized(monkeypatch):
    async def fail_auth(request, token=None):
        raise HTTPException(status_code=401, detail="bad token")

    monkeypatch.setattr("research.routes.authenticate_request", fail_auth)
    client = _make_client()
    with client.websocket_connect("/ws/research") as ws:
        message = ws.receive()
    assert message["type"] == "websocket.close"
    assert message["code"] == 4401


def test_ws_endpoint_pushes_event_and_pongs(monkeypatch):
    async def fake_auth(request, token=None):
        return {"user_id": "u1"}

    monkeypatch.setattr("research.routes.authenticate_request", fake_auth)
    client = _make_client()
    with client.websocket_connect("/ws/research") as ws:
        connected = ws.receive_json()
        assert connected["type"] == "connected"
        assert connected["data"] == {"owner": "u1"}

        # 端点 accept 时已绑定 portal 的事件循环，作为发布目标
        payload = {"session_id": 7, "event": {"seq": 1, "stage": "loop.round", "msg": "m", "ts": 0}}
        research_ws.publish_event("u1", payload)
        pushed = ws.receive_json()
        assert pushed == {"type": "research.event", "data": payload}

        # 心跳约定：任意客户端消息回 pong
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}
    # 连接关闭后，端点的队列已从桥上摘除
    assert "u1" not in research_ws._subscribers
