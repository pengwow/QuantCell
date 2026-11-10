import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# DEBUG 用 fixture + monkeypatch 设置（自动恢复），避免模块级 os.environ
# 泄漏把后续测试（如 ai_model 认证测试）污染成 debug 直通。
@pytest.fixture(autouse=True)
def _debug_mode(monkeypatch):
    monkeypatch.setenv("DEBUG", "true")


@pytest.fixture()
def _model_storage(tmp_path, monkeypatch):
    """把路由内 ModelRegistryService() 的默认存储重定向到临时目录,
    避免端点测试污染真实 data/models;共享缓存按 abspath 键,
    patched init 与测试内显式 storage_path 指向同一注册表。"""
    from services.model_registry import ModelRegistryService

    real_init = ModelRegistryService.__init__

    def patched_init(self, storage_path=str(tmp_path)):
        real_init(self, storage_path)

    monkeypatch.setattr(ModelRegistryService, "__init__", patched_init)


def _register_promoted(tmp_path: str, name: str) -> None:
    """直接经 service 注册并晋升一个模型,artifact 内容固定可断言。"""
    from services.model_registry import ModelRegistryService

    artifact = os.path.join(tmp_path, f"{name}.zip")
    with open(artifact, "wb") as f:
        f.write(b"fake-sb3-bytes")
    svc = ModelRegistryService(storage_path=tmp_path)
    svc.register_model(name=name, model_path=artifact, metrics={"sharpe": 1.2})
    svc.promote_to_production(name)


def test_model_list_endpoint():
    from api.model_routes import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.get("/api/v1/models/list")
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 0
    assert isinstance(data["data"], list)


def test_model_detail_endpoint(tmp_path, _model_storage):
    from api.model_routes import router

    _register_promoted(str(tmp_path), "rl_model_a")
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    resp = client.get("/api/v1/models/rl_model_a/detail")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert set(data.keys()) == {
        "name",
        "version",
        "stage",
        "metadata",
        "metrics",
        "artifact_size_bytes",
        "artifact_hash",
        "storage_uri",
        "algorithm",
        "trained_at",
        "spec_version",
        "window_size",
        "features",
        "observation_stats_present",
        "walk_forward",
    }
    assert data["name"] == "rl_model_a"
    assert data["stage"] == "production"
    assert data["metrics"] == {"sharpe": 1.2}
    # 注册时无 algorithm metadata,名字尾段非纯数字 → 兜底占位
    assert data["algorithm"] == "-"
    # 不存在的模型 → 404
    assert client.get("/api/v1/models/no_such_model/detail").status_code == 404


def test_model_detail_endpoint_unpromoted(tmp_path, _model_storage):
    from api.model_routes import router
    from services.model_registry import ModelRegistryService

    # 注册后不晋升 → service 走 get_latest 兜底,detail 仍 200 且 stage 为真实值
    artifact = os.path.join(str(tmp_path), "dev_model.zip")
    with open(artifact, "wb") as f:
        f.write(b"fake-sb3-bytes")
    ModelRegistryService(storage_path=str(tmp_path)).register_model(
        name="dev_model", model_path=artifact, metrics={"sharpe": 0.5}
    )
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    resp = client.get("/api/v1/models/dev_model/detail")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["name"] == "dev_model"
    assert data["stage"] == "staging"
    assert data["metrics"] == {"sharpe": 0.5}


def test_model_download_endpoint(tmp_path, _model_storage):
    from api.model_routes import router

    _register_promoted(str(tmp_path), "rl_model_b")
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    resp = client.get("/api/v1/models/rl_model_b/download")
    assert resp.status_code == 200
    # FileResponse 返回的字节必须与注册源文件一致
    assert resp.content == b"fake-sb3-bytes"


def test_model_download_development_404(tmp_path, _model_storage):
    from api.model_routes import router
    from services.model_registry import ModelRegistryService

    # 只注册不晋升 → 无 production → 下载 404
    artifact = os.path.join(str(tmp_path), "dev_model.zip")
    with open(artifact, "wb") as f:
        f.write(b"fake")
    ModelRegistryService(storage_path=str(tmp_path)).register_model(name="dev_model", model_path=artifact)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    assert client.get("/api/v1/models/dev_model/download").status_code == 404


def test_model_unpromote_endpoint(tmp_path, _model_storage):
    from api.model_routes import router
    from services.model_registry import ModelRegistryService

    _register_promoted(str(tmp_path), "rl_model_c")
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    resp = client.post("/api/v1/models/rl_model_c/unpromote")
    assert resp.status_code == 200
    assert resp.json()["data"]["success"] is True
    # 取消晋升后 production 落空,detail 走 get_latest 兜底回 staging
    detail = client.get("/api/v1/models/rl_model_c/detail")
    assert detail.status_code == 200
    assert detail.json()["data"]["stage"] == "staging"
    # 无 production(已取消晋升)与不存在的模型 → success=False
    assert client.post("/api/v1/models/rl_model_c/unpromote").json()["data"]["success"] is False
    assert client.post("/api/v1/models/no_such_model/unpromote").json()["data"]["success"] is False
