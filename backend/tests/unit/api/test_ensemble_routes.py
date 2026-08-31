import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# DEBUG 用 fixture + monkeypatch 设置（自动恢复），避免模块级 os.environ
# 泄漏把后续测试（如 ai_model 认证测试）污染成 debug 直通。
@pytest.fixture(autouse=True)
def _debug_mode(monkeypatch):
    monkeypatch.setenv("DEBUG", "true")


def _make_app():
    from api.v2.ensemble_routes import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_ensemble_list_endpoint():
    client = _make_app()
    resp = client.get("/api/v2/ensemble/list")
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    assert isinstance(data["data"], list)


def test_ensemble_create_endpoint():
    client = _make_app()
    resp = client.post(
        "/api/v2/ensemble/create",
        json={"strategy": "soft_vote", "model_paths": ["/tmp/m1"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    assert "ensemble_id" in data["data"]


def test_ensemble_predict_not_found():
    client = _make_app()
    resp = client.post("/api/v2/ensemble/nonexistent/predict", json={"observation": {}})
    assert resp.status_code == 404
