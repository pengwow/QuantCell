"""GET /api/v1/models/unified 聚合逻辑测试(服务层直接调用,走 __init__ 打桩存储)。"""

import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _debug_mode(monkeypatch):
    """裸 app 无官方 token,依赖 tests/unit/api/_debug_mode 风格放行 get_current_user。"""
    monkeypatch.setenv("DEBUG", "true")


@pytest.fixture()
def _model_storage(tmp_path, monkeypatch):
    """路由内 ModelRegistryService() 的默认存储重定向到临时目录(同 test_model_routes)。"""
    from services.model_registry import ModelRegistryService

    real_init = ModelRegistryService.__init__

    def patched_init(self, storage_path=str(tmp_path)):
        real_init(self, storage_path)

    monkeypatch.setattr(ModelRegistryService, "__init__", patched_init)


def _write_zip(base_dir: str, stem: str, payload: bytes = b"fake-sb3-bytes" * 1024) -> str:
    # 默认负载放大到 14KB:size_mb 按 2 位小数取整,14 字节会取整成 0.0,违背本文件 size_mb>0 的断言
    path = os.path.join(base_dir, f"{stem}.zip")
    with open(path, "wb") as f:
        f.write(payload)
    return path


def test_unified_joins_registered_unregistered_and_missing(tmp_path):
    from services.model_registry import ModelRegistryService

    registered_zip = _write_zip(str(tmp_path), "boll_1000_ppo_1782404770")
    _write_zip(str(tmp_path), "fresh_only_ppo_1782404780")
    svc = ModelRegistryService(storage_path=str(tmp_path))
    svc.register_model(
        name="boll_1000_ppo_1782404770",
        model_path=registered_zip,
        metadata={"algorithm": "ppo", "created_at": "2026-11-10T12:00:00.000+08:00"},
        metrics={"sharpe_ratio": 1.82},
    )
    # 文件缺失条目:artifact 放 artifacts 子目录避开顶层 *.zip 扫描
    art_dir = os.path.join(str(tmp_path), "artifacts")
    os.makedirs(art_dir, exist_ok=True)
    ghost_zip = _write_zip(art_dir, "ghost_src")
    svc.register_model(
        name="ghost_model",
        model_path=ghost_zip,
        metadata={"created_at": "2026-11-09T09:00:00.000+08:00"},
    )

    rows = svc.list_unified_models()
    by_file = {r["file_name"]: r for r in rows}

    # 1) 已注册且有文件:注册名 == stem join 命中
    joined = by_file["boll_1000_ppo_1782404770.zip"]
    assert joined["registered"] is True
    assert joined["model_id"] == "boll_1000_ppo_1782404770"
    assert joined["stage"] == "staging"
    assert joined["algorithm"] == "ppo"
    assert joined["metrics"] == {"sharpe_ratio": 1.82}
    assert joined["size_mb"] > 0
    assert isinstance(joined["created"], float)

    # 2) 未注册文件:algorithm 从文件名 {..}_{algo}_{unixts} 推断
    unreg = by_file["fresh_only_ppo_1782404780.zip"]
    assert unreg["registered"] is False
    assert unreg["model_id"] is None
    assert unreg["stage"] == ""
    assert unreg["algorithm"] == "ppo"
    assert unreg["metrics"] == {}
    assert unreg["size_mb"] is not None
    assert isinstance(unreg["created"], float)

    # 3) 文件缺失条目:保留展示,size 为空,created 回退条目 metadata.created_at
    missing = by_file["ghost_model.zip"]
    assert missing["registered"] is True
    assert missing["size_mb"] is None
    assert isinstance(missing["created"], float)

    assert len(rows) == 3


def test_unified_join_by_metadata_model_path(tmp_path):
    from services.model_registry import ModelRegistryService

    zip_path = _write_zip(str(tmp_path), "renamed_artifact")
    svc = ModelRegistryService(storage_path=str(tmp_path))
    # 注册名与 stem 不同,靠 metadata.model_path join
    svc.register_model(name="custom_name", model_path=zip_path, metadata={"model_path": zip_path})

    rows = svc.list_unified_models()
    assert len(rows) == 1
    assert rows[0]["registered"] is True
    assert rows[0]["file_name"] == "renamed_artifact.zip"
    assert rows[0]["model_id"] == "custom_name"


def test_unified_same_zip_prefers_latest_created(tmp_path):
    from services.model_registry import ModelRegistryService

    zip_path = _write_zip(str(tmp_path), "shared_file")
    svc = ModelRegistryService(storage_path=str(tmp_path))
    svc.register_model(
        name="older_entry",
        model_path=zip_path,
        metadata={"model_path": zip_path, "created_at": "2026-01-01T00:00:00.000+08:00"},
    )
    svc.register_model(
        name="newer_entry",
        model_path=zip_path,
        metadata={"model_path": zip_path, "created_at": "2026-06-01T00:00:00.000+08:00"},
    )

    rows = svc.list_unified_models()
    assert len(rows) == 1
    assert rows[0]["model_id"] == "newer_entry"


def test_unified_empty_or_missing_dir(tmp_path):
    from services.model_registry import ModelRegistryService

    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    assert ModelRegistryService(storage_path=str(empty_dir)).list_unified_models() == []

    # 目录不存在:glob 返回空,不抛异常
    assert ModelRegistryService(storage_path=str(tmp_path / "not_exists")).list_unified_models() == []


def test_unified_rows_sorted_by_created_desc(tmp_path):
    from services.model_registry import ModelRegistryService

    old_file = _write_zip(str(tmp_path), "a_old_file")
    new_file = _write_zip(str(tmp_path), "z_new_file")
    os.utime(old_file, (1000, 1000))  # 显式压旧 mtime/ctime 相近值
    os.utime(new_file, (2000, 2000))
    svc = ModelRegistryService(storage_path=str(tmp_path))

    rows = svc.list_unified_models()
    created_list = [r["created"] for r in rows]
    assert created_list == sorted(created_list, reverse=True)
    assert rows[0]["file_name"] == "z_new_file.zip"


def test_unified_endpoint(tmp_path, _model_storage):
    registered_zip = _write_zip(str(tmp_path), "api_model")
    from services.model_registry import ModelRegistryService

    svc = ModelRegistryService(storage_path=str(tmp_path))
    svc.register_model(name="api_model", model_path=registered_zip, metrics={"sharpe_ratio": 1.1})
    # 路由内的 ModelRegistryService() 由 _model_storage fixture 打桩到同一 tmp 目录,
    # 底层 registry 按 abspath 共享,能读到刚才注册的条目
    from api.model_routes import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    resp = client.get("/api/v1/models/unified")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    assert isinstance(data, list) and len(data) == 1
    assert data[0]["registered"] is True
    assert data[0]["model_id"] == "api_model"
    assert data[0]["metrics"] == {"sharpe_ratio": 1.1}
