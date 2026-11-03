"""GET /api/v1/workers/{id}/decisions 与 /decisions/detail 的契约测试。"""

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from strategy import decision_recording
from utils.auth import get_current_user
from worker.dependencies import get_db_session
from worker.routes import crud, router


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("QUANTCELL_DECISION_REPLAY_DIR", str(tmp_path))
    # worker 存在性不查真实库；HTTPException 会由装饰器原样透传
    monkeypatch.setattr(crud, "get_worker", lambda db, wid: object())
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db_session] = lambda: None
    app.dependency_overrides[get_current_user] = lambda: {"sub": "test"}
    return TestClient(app)


def _write(lines):
    p = decision_recording.worker_replay_path(1)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _line(fp, action, ts):
    return json.dumps(
        {
            "fingerprint": fp,
            "decision": {"action": action, "confidence": 0.5},
            "state": {},
            "questions": {},
            "ts": ts,
            "_decider": "规则",
        }
    )


def test_list_returns_recent_first(client):
    _write([_line("a" * 64, "hold", "2026-01-01"), _line("b" * 64, "buy", "2026-01-02")])
    r = client.get("/api/v1/workers/1/decisions?limit=1").json()
    assert r["code"] == 0
    assert r["data"]["total"] == 2
    assert [d["_ts"] for d in r["data"]["decisions"]] == ["2026-01-02"]
    assert r["data"]["decisions"][0]["_seq"] == 1


def test_list_empty_when_no_recording(client):
    assert client.get("/api/v1/workers/9/decisions").json()["data"]["decisions"] == []


def test_detail_hit(client):
    _write([_line("a" * 64, "buy", "t")])
    r = client.get(f"/api/v1/workers/1/decisions/detail?seq=0&fingerprint={'a' * 64}").json()
    assert r["code"] == 0 and r["data"]["decision"]["action"] == "buy"


def test_detail_fingerprint_mismatch(client):
    _write([_line("a" * 64, "hold", "t")])
    r = client.get(f"/api/v1/workers/1/decisions/detail?seq=0&fingerprint={'b' * 64}").json()
    assert r["code"] == 1 and "未命中" in r["message"]
