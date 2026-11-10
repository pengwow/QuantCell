import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# DEBUG 直通(鉴权)+ 服务隔离:ENSEMBLES_STORE 指向 tmp、清空 lru_cache 单例,
# 防止测试写入真实 backend/data/ensembles.json 或跨用例串数据。
@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DEBUG", "true")
    from services import ensemble_service as es

    monkeypatch.setattr(es, "ENSEMBLES_STORE", tmp_path / "ensembles.json")
    es.get_ensemble_service.cache_clear()
    yield
    es.get_ensemble_service.cache_clear()


def _make_app():
    from api.ensemble_routes import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_ensemble_list_endpoint():
    client = _make_app()
    resp = client.get("/api/v1/ensemble/list")
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    assert isinstance(data["data"], list)


def test_ensemble_create_endpoint():
    client = _make_app()
    resp = client.post(
        "/api/v1/ensemble/create",
        json={"strategy": "soft_vote", "model_paths": ["/tmp/m1"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    assert "ensemble_id" in data["data"]
    # /tmp/m1 不存在 → 被跳过,响应需带回 skipped 明细
    assert len(data["data"]["skipped"]) == 1


def test_ensemble_delete_endpoint():
    client = _make_app()
    resp = client.post("/api/v1/ensemble/create", json={"strategy": "soft_vote", "model_paths": []})
    eid = resp.json()["data"]["ensemble_id"]

    resp = client.delete(f"/api/v1/ensemble/{eid}")
    assert resp.status_code == 200
    assert resp.json()["code"] == 0

    # 删除后再删 → 404
    resp = client.delete(f"/api/v1/ensemble/{eid}")
    assert resp.status_code == 404


def test_ensemble_delete_not_found():
    client = _make_app()
    resp = client.delete("/api/v1/ensemble/nonexistent")
    assert resp.status_code == 404


def test_ensemble_predict_not_found():
    client = _make_app()
    resp = client.post("/api/v1/ensemble/nonexistent/predict", json={"observation": {}})
    assert resp.status_code == 404
