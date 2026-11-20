"""GET/POST /agent/chat/stream 回归：content 事件 data 为 dict 时生成器不得炸。

真机走查实锤的 bug：loop 的 content 事件 data 是 {"content", "full_content"} dict，
routes 的 `accumulated_content += event.data` 抛 TypeError → 客户端永远只收到
error 事件（"can only concatenate str ..."），LLM 正常回复也被吞。
"""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent.core.events import StreamEvent

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _debug_auth(monkeypatch):
    """与其他 api 路由测试同口径：DEBUG 下鉴权直通。"""
    monkeypatch.setenv("DEBUG", "true")


def _stub_agent():
    class _StubAgent:
        async def iter_message_stream(
            self, content: str, session_key: str = "default", extra_context: str | None = None
        ):
            # loop 实际形状：content 事件 data 是 dict；同时容忍 str 数据
            yield StreamEvent(event_type="content", data={"content": "1", "full_content": "1"})
            yield StreamEvent(event_type="content", data={"content": "+1", "full_content": "1+1"})
            yield StreamEvent(event_type="content", data="legacy-str")
            yield StreamEvent(
                event_type="complete",
                data={"answer": "1+1=2"},
            )

    return _StubAgent()


def _client_with(monkeypatch) -> TestClient:
    from agent.api import routes as agent_routes

    monkeypatch.setattr(agent_routes, "get_agent", lambda: _stub_agent())
    app = FastAPI()
    app.include_router(agent_routes.router)
    return TestClient(app)


def test_stream_survives_dict_content_events(monkeypatch):
    client = _client_with(monkeypatch)
    resp = client.post(
        "/api/v1/agent/chat/stream",
        json={"message": "1+1等于几", "session_id": "t1"},
    )
    assert resp.status_code == 200
    body = resp.text

    events = [line[7:].strip() for line in body.splitlines() if line.startswith("event: ")]
    assert "error" not in events, f"不应有 error 事件: {body[:300]}"
    assert events.count("content") == 3
    assert "complete" in events

    # 累积内容只取 dict 的 content 键，complete 的结构化提取基于纯文本
    content_payloads = [
        json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: ") and '"content"' in line
    ]
    assert any(p["data"] == {"content": "1", "full_content": "1"} for p in content_payloads)
