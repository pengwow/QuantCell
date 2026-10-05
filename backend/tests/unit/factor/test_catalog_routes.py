"""因子档案/生命周期/快照 HTTP 测试（走真实应用，临时快照目录由服务默认目录承载）。

保存快照依赖 analyze 全链路，故与 test_factor_routes 一样要求本地有 BTCUSDT 1h。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from utils import get_source_data_dir
from utils.auth import get_current_user

if not (get_source_data_dir() / "crypto/spot/klines/1h/BTCUSDT.parquet").exists():
    pytest.skip("本地无 BTCUSDT 1h parquet，跳过档案 HTTP 检查", allow_module_level=True)

from main import app


def _client() -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: {"username": "e2e", "id": 1}
    return TestClient(app)


def test_catalog_lists_builtins():
    client = _client()
    try:
        r = client.get("/api/v1/factor/catalog")
        assert r.status_code == 200, r.text
        items = r.json()["data"]["factors"]
        names = {x["name"] for x in items}
        assert {"close", "momentum_5d"} <= names
        assert all(x["lifecycle_status"] for x in items)
    finally:
        app.dependency_overrides.clear()


def test_builtin_lifecycle_forbidden_and_unknown_404():
    client = _client()
    try:
        r = client.post("/api/v1/factor/catalog/close/lifecycle", json={"status": "INSPECTED"})
        assert r.status_code == 403
        r2 = client.post("/api/v1/factor/catalog/ghost/lifecycle", json={"status": "INSPECTED"})
        assert r2.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_custom_factor_full_lifecycle_flow():
    client = _client()
    try:
        # 新建自定义因子 → 自动建档 DISCOVERED
        assert (
            client.post(
                "/api/v1/factor/add", json={"factor_name": "zz_lifecycle_demo", "expression": "close-open"}
            ).status_code
            == 200
        )
        r = client.post("/api/v1/factor/catalog/zz_lifecycle_demo/lifecycle", json={"status": "INSPECTED"})
        assert r.status_code == 200, r.text
        # 非法跳跃
        bad = client.post("/api/v1/factor/catalog/zz_lifecycle_demo/lifecycle", json={"status": "LIVE"})
        assert bad.status_code == 400
        # 退役后终态
        assert (
            client.post("/api/v1/factor/catalog/zz_lifecycle_demo/lifecycle", json={"status": "RETIRED"}).status_code
            == 200
        )
        assert (
            client.post("/api/v1/factor/catalog/zz_lifecycle_demo/lifecycle", json={"status": "INSPECTED"}).status_code
            == 400
        )
        # 清理：删除自定义因子（档案与快照钩子级联）
        assert client.delete("/api/v1/factor/delete/zz_lifecycle_demo").status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_snapshot_save_list_delete():
    client = _client()
    try:
        body = {
            "factor_name": "close",
            "instruments": ["BTCUSDT"],
            "interval": "1h",
            "candle_type": "spot",
            "start_time": None,
            "end_time": None,
            "method": "spearman",
            "n_groups": 5,
            "window": 20,
            "forward": 1,
        }
        r = client.post("/api/v1/factor/snapshots", json=body)
        assert r.status_code == 200, r.text
        sid = r.json()["data"]["id"]
        listing = client.get("/api/v1/factor/snapshots", params={"factor_name": "close"}).json()["data"]["snapshots"]
        assert any(x["id"] == sid for x in listing)
        assert client.delete(f"/api/v1/factor/snapshots/{sid}").status_code == 200
        assert client.delete(f"/api/v1/factor/snapshots/{sid}").status_code == 404
    finally:
        app.dependency_overrides.clear()
