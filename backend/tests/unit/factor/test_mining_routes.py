# 代码因子与 LLM 挖掘路由测试（鉴权/客户端模式复刻 test_async_job_routes.py）
#
# 说明：
# - /code/validate 走沙箱合成数据（真实子进程，约 1 秒，不依赖本地 parquet）；
# - /mine/llm 用 monkeypatch 替换 job_manager.submit 与 _resolve_llm_config，
#   不打真实 LLM、不跑真实线程池，因此本文件不做模块级 skip。

import pytest
from fastapi.testclient import TestClient

from main import app
from utils.auth import get_current_user


@pytest.fixture
def client():
    app.dependency_overrides[get_current_user] = lambda: {"username": "t", "id": 1}
    c = TestClient(app)
    yield c
    app.dependency_overrides.clear()


def test_validate_code_ok(client):
    resp = client.post(
        "/api/v1/factor/code/validate",
        json={"code": 'factor = df["close"].pct_change(5)'},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["valid"] is True


def test_validate_code_rejects_import(client):
    resp = client.post("/api/v1/factor/code/validate", json={"code": "import os"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["valid"] is False
    assert data["error_type"]


def test_add_and_delete_code_factor(client, tmp_path, monkeypatch):
    # 用临时 code store 隔离全局文件：monkeypatch factor_service._code_store
    from factor.code_store import CodeFactorStore
    from factor.routes import factor_service

    monkeypatch.setattr(factor_service, "_code_store", CodeFactorStore(tmp_path / "c.json"))
    resp = client.post(
        "/api/v1/factor/code/add",
        json={
            "factor_name": "llm_demo_1",
            "code": 'factor = df["close"].rolling(10).mean() / df["close"] - 1',
            "description": "demo",
        },
    )
    assert resp.status_code == 200, resp.text
    assert client.delete("/api/v1/factor/code/llm_demo_1").status_code == 200


def test_add_code_factor_rejects_bad_code(client):
    resp = client.post(
        "/api/v1/factor/code/add",
        json={"factor_name": "x", "code": "import os"},
    )
    assert resp.status_code == 400


def test_mine_llm_submits_job(client, monkeypatch):
    submitted = {}

    def fake_submit(kind, params, runner):
        submitted["kind"] = kind
        submitted["params"] = params
        return "job-123"

    monkeypatch.setattr("factor.routes.job_manager.submit", fake_submit)
    monkeypatch.setattr(
        "factor.routes._resolve_llm_config",
        lambda model_id=None: {"api_key": "k", "base_url": "http://x", "model": "m"},
    )
    resp = client.post(
        "/api/v1/factor/mine/llm",
        json={
            "instruments": ["BTCUSDT", "ETHUSDT"],
            "interval": "1h",
            "candle_type": "spot",
            "start_time": None,
            "end_time": None,
            "n_candidates": 3,
            "n_rounds": 2,
            "top_k": 5,
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["job_id"] == "job-123"
    assert submitted["kind"] == "llm_mine"


def test_mine_llm_without_model_config_400(client, monkeypatch):
    monkeypatch.setattr("factor.routes._resolve_llm_config", lambda model_id=None: None)
    resp = client.post(
        "/api/v1/factor/mine/llm",
        json={"instruments": ["BTCUSDT"], "interval": "1h"},
    )
    assert resp.status_code == 400
