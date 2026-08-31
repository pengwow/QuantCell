import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# DEBUG 用 fixture + monkeypatch 设置（自动恢复），避免模块级 os.environ
# 泄漏把后续测试（如 ai_model 认证测试）污染成 debug 直通。
@pytest.fixture(autouse=True)
def _debug_mode(monkeypatch):
    monkeypatch.setenv("DEBUG", "true")


def test_model_list_endpoint():
    from api.v2.model_routes import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.get("/api/v2/models/list")
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 0
    assert isinstance(data["data"], list)
