"""因子异步任务 HTTP 测试（真实 parquet；无数据则模块 skip）。

后台线程任务用「轮询到终态」等待，不硬 sleep。
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from utils import get_source_data_dir
from utils.auth import get_current_user

if not (get_source_data_dir() / "crypto/spot/klines/1h/BTCUSDT.parquet").exists():
    pytest.skip("本地无 BTCUSDT 1h parquet，跳过异步任务 HTTP 检查", allow_module_level=True)

import factor.routes as factor_routes
from factor.models import FactorSnapshot
from main import app
from utils.db_session import get_db_session


def _client() -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: {"username": "e2e", "id": 1}
    return TestClient(app)


def _wait_job(client: TestClient, job_id: str, timeout: float = 20.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = client.get(f"/api/v1/factor/jobs/{job_id}")
        assert r.status_code == 200
        st = r.json()["data"]
        if st["status"] in ("completed", "failed"):
            return st
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} 超时")


ANALYZE_BODY = {
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


def test_analyze_async_completes_and_result_fetchable():
    client = _client()
    before = _snapshot_ids()
    new_ids: set[int] = set()
    try:
        r = client.post("/api/v1/factor/analyze-async", json=ANALYZE_BODY)
        assert r.status_code == 200, r.text
        jid = r.json()["data"]["job_id"]

        st = _wait_job(client, jid)
        assert st["status"] == "completed"
        assert st["progress"] == 100.0
        assert "result" not in st  # 状态查询不泄露结果

        rr = client.get(f"/api/v1/factor/jobs/{jid}/result")
        assert rr.status_code == 200
        data = rr.json()["data"]
        assert data["factor_name"] == "close"
        assert "inspection" in data
        # 强制留痕：普通分析（无任何开关入参）也会落一条快照
        new_ids = _snapshot_ids() - before
        assert len(new_ids) == 1
    finally:
        # 清理本用例产生的快照（走 DELETE 接口，parquet 同步归档）
        for sid in new_ids:
            client.delete(f"/api/v1/factor/snapshots/{sid}")
        app.dependency_overrides.clear()


def test_compare_async_returns_two_factors():
    client = _client()
    try:
        body = {k: v for k, v in ANALYZE_BODY.items() if k != "factor_name"}
        body["factor_names"] = ["momentum_5d", "rsi_14d"]
        body["instruments"] = ["BTCUSDT", "ETHUSDT"]

        r = client.post("/api/v1/factor/compare-async", json=body)
        assert r.status_code == 200, r.text
        jid = r.json()["data"]["job_id"]

        st = _wait_job(client, jid)
        assert st["status"] == "completed"

        data = client.get(f"/api/v1/factor/jobs/{jid}/result").json()["data"]
        assert {f["factor_name"] for f in data["factors"]} == {"momentum_5d", "rsi_14d"}
        assert len(data["ic_series"]["dates"]) == len(data["ic_series"]["series"]["momentum_5d"])
    finally:
        app.dependency_overrides.clear()


def test_failed_job_result_is_410_and_unknown_404():
    client = _client()
    try:
        body = dict(ANALYZE_BODY, factor_name="ghost_factor")
        r = client.post("/api/v1/factor/analyze-async", json=body)
        assert r.status_code == 200, r.text
        jid = r.json()["data"]["job_id"]

        st = _wait_job(client, jid)
        assert st["status"] == "failed"
        assert "ghost_factor" in (st["error"] or "")

        rr = client.get(f"/api/v1/factor/jobs/{jid}/result")
        assert rr.status_code == 410
        assert "ghost_factor" in rr.json()["detail"]

        assert client.get("/api/v1/factor/jobs/not-exist-id").status_code == 404
    finally:
        app.dependency_overrides.clear()


def _snapshot_ids(factor_name: str = "close") -> set[int]:
    """直接查快照表当前 id 集合，用于比对自动留痕是否多了一行。"""
    with get_db_session() as db:
        return {r.id for r in db.query(FactorSnapshot).filter_by(factor_name=factor_name).all()}


def test_analyze_async_snapshot_failure_is_best_effort(monkeypatch):
    def _boom(*args, **kwargs):
        raise RuntimeError("disk full")

    # 强制留痕无开关：runner 在工作线程内通过模块级 _catalog_service 调落库，
    # patch 实例方法模拟落库失败，断言分析任务本身仍 completed
    monkeypatch.setattr(factor_routes._catalog_service, "save_snapshot_from_result", _boom)

    client = _client()
    try:
        r = client.post("/api/v1/factor/analyze-async", json=ANALYZE_BODY)
        assert r.status_code == 200, r.text
        jid = r.json()["data"]["job_id"]

        st = _wait_job(client, jid)
        assert st["status"] == "completed"
        rr = client.get(f"/api/v1/factor/jobs/{jid}/result")
        assert rr.status_code == 200
        assert rr.json()["data"]["factor_name"] == "close"
    finally:
        app.dependency_overrides.clear()
