"""P4-3 自动重训闭环薄路由测试（只测 HTTP 契约，不跑训练）。"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.retrain_policy import RetrainCandidate


@pytest.fixture(autouse=True)
def _debug_mode(monkeypatch):
    """与 test_rl_routes 同口径：DEBUG 下鉴权直通。"""
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.delenv("QUANTCELL_AUTO_RETRAIN", raising=False)
    monkeypatch.delenv("QUANTCELL_AUTO_PROMOTE", raising=False)


def _client() -> TestClient:
    from api.rl_routes import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _candidate() -> RetrainCandidate:
    return RetrainCandidate(
        family="BTCUSDT",
        model_id="BTCUSDT_v1_ppo_1700000000",
        model_path="/tmp/BTCUSDT_v1_ppo_1700000000.zip",
        reason="oos_decay",
        evidence={"oos_sharpe": 0.4, "train_sharpe": 2.0},
    )


def test_lifecycle_state_exposes_gates_and_candidates(monkeypatch):
    monkeypatch.setenv("QUANTCELL_AUTO_RETRAIN", "1")
    monkeypatch.setattr(
        "services.retrain_policy.select_retrain_candidates",
        lambda *args, **kwargs: [_candidate()],
    )
    monkeypatch.setattr("rl.lifecycle.pending_promotions", lambda *args, **kwargs: [{"challenger_id": "c1"}])
    monkeypatch.setattr(
        "rl.lifecycle.load_lifecycle_state",
        lambda *args, **kwargs: {"shadow": {"BTCUSDT": [{"winner": "challenger"}]}, "promotions": []},
    )

    resp = _client().get("/api/v1/rl/lifecycle/state")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["auto_retrain_enabled"] is True
    assert data["auto_promote_enabled"] is False  # 第二道闸默认关
    assert data["candidates"][0]["family"] == "BTCUSDT"
    assert data["candidates"][0]["reason"] == "oos_decay"
    assert data["pending_promotions"] == [{"challenger_id": "c1"}]
    assert data["shadow"]["BTCUSDT"][0]["winner"] == "challenger"


def test_lifecycle_run_dry_run_does_not_train(monkeypatch):
    monkeypatch.setattr(
        "services.retrain_policy.select_retrain_candidates",
        lambda *args, **kwargs: [_candidate()],
    )
    called: list = []
    monkeypatch.setattr(
        "rl.lifecycle.run_auto_retrain_cycle",
        lambda *args, **kwargs: called.append(True) or {},
    )

    resp = _client().post("/api/v1/rl/lifecycle/run", json={})

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["dry_run"] is True
    assert data["candidates"][0]["model_id"] == "BTCUSDT_v1_ppo_1700000000"
    assert "max_per_day" in data["policy"]
    assert called == []


def test_lifecycle_run_executes_cycle(monkeypatch):
    summary = {"checked_at": "2026-11-18T03:40:00+00:00", "candidates": [], "results": []}
    monkeypatch.setattr("rl.lifecycle.run_auto_retrain_cycle", lambda *args, **kwargs: summary)

    resp = _client().post("/api/v1/rl/lifecycle/run", json={"dry_run": False})

    assert resp.status_code == 200
    assert resp.json()["message"] == "闭环执行完成"
    assert resp.json()["data"] == summary
