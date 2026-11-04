"""研究路由契约测试：创建/列表/详情/暂停/继续/取消/继续研究/并发上限。"""

from __future__ import annotations

from contextlib import contextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import strategy.models  # 注册 Strategy，保证 Worker 关系的 mapper 可初始化
from collector.db.database import Base
from research import routes as research_routes
from research import service
from research.models import ResearchEvent, ResearchKnowledge, ResearchSession, ResearchTrial
from utils.auth import get_current_user


@pytest.fixture()
def client(monkeypatch):
    # TestClient 在独立线程执行请求，内存库需要允许多线程共享连接
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
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
    def fake_db():
        yield db

    monkeypatch.setattr(research_routes, "get_db_session", fake_db)
    monkeypatch.setattr(
        research_routes,
        "_resolve_llm",
        lambda model_id=None: {"api_key": "k", "base_url": "u", "model": "m"},
    )
    monkeypatch.setattr(research_routes, "_start_job", lambda **kwargs: "job-test")

    app = FastAPI()
    app.include_router(research_routes.router, prefix="/api/v1")
    # 过渡期旧前缀 alias（与 factor.routes 的挂载方式一致）
    app.include_router(research_routes.router, prefix="/api/v1/factor")
    app.dependency_overrides[get_current_user] = lambda: {"user_id": "u1"}
    try:
        yield TestClient(app), db
    finally:
        db.close()


PAYLOAD = {
    "mode": "deep",
    "symbols": ["BTCUSDT"],
    "interval": "1h",
    "candle_type": "spot",
    "start": "2026-01-01",
    "end": "2026-06-01",
}


def _create(client, **extra) -> int:
    res = client.post("/api/v1/research/sessions", json={**PAYLOAD, **extra})
    assert res.status_code == 200, res.text
    return res.json()["data"]["session_id"]


def test_create_list_detail(client):
    tc, db = client
    sid = _create(tc, mode="quick", loop_n=1)
    row = db.get(ResearchSession, sid)
    assert row.status == "running"
    assert row.backend_job_id == "job-test"

    res = tc.get("/api/v1/research/sessions")
    assert res.status_code == 200
    body = res.json()["data"]
    assert body["total"] == 1
    assert body["sessions"][0]["mode"] == "quick"

    detail = tc.get(f"/api/v1/research/sessions/{sid}").json()["data"]
    assert detail["status"] == "running"
    assert detail["trials"] == []
    assert detail["config"]["loop_n"] == 1


def test_window_and_quick_loop_validation(client):
    tc, _ = client
    bad_window = {**PAYLOAD, "start": "2026-01-01", "end": "2026-01-20"}
    assert tc.post("/api/v1/research/sessions", json=bad_window).status_code == 422
    assert tc.post("/api/v1/research/sessions", json={**PAYLOAD, "mode": "quick", "loop_n": 2}).status_code == 422


def test_pause_resume_cancel(client):
    tc, db = client
    sid = _create(tc)

    assert tc.post(f"/api/v1/research/sessions/{sid}/pause").status_code == 200
    assert db.get(ResearchSession, sid).status == "paused"

    assert tc.post(f"/api/v1/research/sessions/{sid}/resume").status_code == 200
    assert db.get(ResearchSession, sid).status == "running"

    assert tc.post(f"/api/v1/research/sessions/{sid}/cancel").status_code == 200
    assert db.get(ResearchSession, sid).status == "cancelled"
    # 终态不可再暂停
    assert tc.post(f"/api/v1/research/sessions/{sid}/pause").status_code == 409


def test_extend_only_deep_and_only_completed(client):
    tc, db = client
    sid = _create(tc, mode="deep")
    row = db.get(ResearchSession, sid)
    service.set_session_status(db, row, "completed")

    res = tc.post(f"/api/v1/research/sessions/{sid}/extend", json={"extra_loops": 2})
    assert res.status_code == 200
    cfg = service.session_config(db.get(ResearchSession, sid))
    assert cfg["loop_n"] == 5  # 默认 3 轮 + 追加 2
    assert db.get(ResearchSession, sid).status == "running"

    quick_id = _create(tc, mode="quick")
    qrow = db.get(ResearchSession, quick_id)
    service.set_session_status(db, qrow, "completed")
    assert tc.post(f"/api/v1/research/sessions/{quick_id}/extend", json={}).status_code == 409


def test_active_session_limit(client):
    tc, _ = client
    first = _create(tc)
    second = _create(tc)
    assert first != second
    third = tc.post("/api/v1/research/sessions", json=PAYLOAD)
    assert third.status_code == 429


def test_old_prefix_alias_still_works(client):
    """P0.5 验收①：旧前缀过渡期仍可用。"""
    tc, _ = client
    sid = _create(tc)
    assert tc.get(f"/api/v1/factor/research/sessions/{sid}").status_code == 200


def test_unsupported_scenario_returns_400(client):
    tc, _ = client
    res = tc.post("/api/v1/research/sessions", json={**PAYLOAD, "scenario": "model"})
    assert res.status_code == 400
    assert res.json()["detail"]["code"] == "scenario_not_supported"


def test_quick_pause_is_rejected(client):
    tc, db = client
    sid = _create(tc, mode="quick", loop_n=1)
    res = tc.post(f"/api/v1/research/sessions/{sid}/pause")
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "pause_unsupported"
    assert db.get(ResearchSession, sid).status == "running"


def test_events_supports_after_seq_incremental(client):
    """事件持久化后按 seq 严格增量返回，跨进程（多 worker）也能读到。"""
    tc, db = client
    sid = _create(tc)
    service.append_event(db, sid, "info", "loop", "第 1 轮开始")
    service.append_event(db, sid, "info", "trial", "候选生成完成")

    first = tc.get(f"/api/v1/research/sessions/{sid}/events", params={"after_seq": 0}).json()["data"]
    assert [e["seq"] for e in first["events"]] == [1, 2]
    assert first["next_seq"] == 2

    service.append_event(db, sid, "info", "judge", "硬门判定完成")
    second = tc.get(f"/api/v1/research/sessions/{sid}/events", params={"after_seq": first["next_seq"]}).json()["data"]
    # next_seq=2 表示 seq<=2 已消费，严格增量只返回新增的 3
    assert [e["seq"] for e in second["events"]] == [3]
    assert second["next_seq"] == 3


def test_events_unknown_job_returns_empty(client):
    tc, _ = client
    sid = _create(tc)
    data = tc.get(f"/api/v1/research/sessions/{sid}/events").json()["data"]
    assert data == {"session_id": sid, "events": [], "next_seq": 0}


def test_create_rejects_over_budget_returns_422(client):
    """创建时按候选数/轮次预扣估算，超预算直接 422，不落会话、不提交作业。"""
    tc, db = client
    res = tc.post("/api/v1/research/sessions", json={**PAYLOAD, "max_llm_calls": 5})
    assert res.status_code == 422, res.text
    assert "LLM 调用" in res.json()["detail"]
    assert db.query(ResearchSession).count() == 0


def test_create_without_llm_returns_409_and_creates_nothing(client, monkeypatch):
    """未配置可用模型时必须在创建阶段明确拒绝，不能建完再在后台静默失败。"""
    tc, db = client
    monkeypatch.setattr(research_routes, "_resolve_llm", lambda model_id=None: None)

    res = tc.post("/api/v1/research/sessions", json={**PAYLOAD, "mode": "quick", "loop_n": 1})

    assert res.status_code == 409, res.text
    detail = res.json()["detail"]
    assert detail["code"] == "llm_unavailable"
    assert "模型" in detail["message"]
    # 关键：不留下 pending/running 的孤儿会话，也没有启动后台作业
    assert db.query(ResearchSession).count() == 0
