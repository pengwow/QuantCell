"""observability 指标埋点单测（P2-01）

覆盖验收要求：开关关闭时端点 404、开启时返回 Prometheus 文本格式、
route 模板化 label 防高基数（具体 worker_id 不入 label）、未匹配路由记
unmatched、异常路径记 500、worker 侧泵轮耗时/同步失败/重启计数辅助函数。
"""

from __future__ import annotations

import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from observability import metrics as obs
from observability.http import MetricsMiddleware
from observability.routes import router as metrics_router
from utils import config_manager


def _sample(name: str, labels: dict[str, str] | None = None) -> float | None:
    return REGISTRY.get_sample_value(name, labels)


def _make_app() -> FastAPI:
    """最小 app：不导入 main.py（重依赖链），只验埋点与端点行为本身"""
    app = FastAPI()
    app.add_middleware(MetricsMiddleware)
    app.include_router(metrics_router)

    @app.get("/api/v1/workers/{worker_id}")
    def fake_worker(worker_id: int):
        return {"ok": True}

    @app.get("/boom")
    def boom():
        raise RuntimeError("boom")

    return app


@pytest.fixture()
def flag(monkeypatch):
    """控制 observability.metrics_enabled 的读取结果（get_flag 内调 get_value）

    用模块对象 patch 而非 "utils.config_manager.get_value" 字符串推导：
    字符串推导在首测阶段会 fresh-import 该模块（其 import 链存在初级环），
    触发 partially initialized ImportError。
    """
    holder = {"on": True}
    monkeypatch.setattr(config_manager, "get_value", lambda dotted_key, default=None: holder["on"])
    return holder


def test_endpoint_404_when_disabled(flag):
    flag["on"] = False
    with TestClient(_make_app()) as client:
        assert client.get("/api/v1/metrics").status_code == 404


def test_default_off_without_config_override():
    """不 patch 配置：config.toml 默认 metrics_enabled=false，端点必须 404"""
    with TestClient(_make_app()) as client:
        assert client.get("/api/v1/metrics").status_code == 404


def test_middleware_passthrough_when_disabled(flag):
    """开关关闭：中间件直通零埋点，业务请求不产生计数样本"""
    flag["on"] = False
    labels = {"route": "/api/v1/workers/{worker_id}", "method": "GET", "status": "200"}
    before = _sample("qc_http_requests_total", labels)
    with TestClient(_make_app()) as client:
        assert client.get("/api/v1/workers/7").status_code == 200
    assert _sample("qc_http_requests_total", labels) == before


def test_endpoint_returns_prometheus_text(flag):
    with TestClient(_make_app()) as client:
        assert client.get("/api/v1/workers/7").status_code == 200
        resp = client.get("/api/v1/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    assert b"qc_http_requests_total" in resp.content
    # 在途 gauge 在请求完成后必须归零（inc/dec 配对）
    assert _sample("qc_http_in_progress") == 0.0


def test_route_label_is_templated(flag):
    """参数化的具体值（12345）不得进入 route label，统一用模板占位"""
    with TestClient(_make_app()) as client:
        client.get("/api/v1/workers/12345")
    templated = _sample(
        "qc_http_requests_total",
        {"route": "/api/v1/workers/{worker_id}", "method": "GET", "status": "200"},
    )
    assert templated is not None and templated >= 1.0
    assert (
        _sample(
            "qc_http_requests_total",
            {"route": "/api/v1/workers/12345", "method": "GET", "status": "200"},
        )
        is None
    )


def test_unmatched_route_labeled_unmatched(flag):
    with TestClient(_make_app()) as client:
        client.get("/no/such/path")
    assert (
        _sample(
            "qc_http_requests_total",
            {"route": "unmatched", "method": "GET", "status": "404"},
        )
        >= 1.0
    )


def test_exception_recorded_as_500(flag):
    with TestClient(_make_app(), raise_server_exceptions=False) as client:
        assert client.get("/boom").status_code == 500
    assert (
        _sample(
            "qc_http_requests_total",
            {"route": "/boom", "method": "GET", "status": "500"},
        )
        >= 1.0
    )


def test_observe_pump_round_records_sample():
    obs.observe_pump_round(99001, "paper", time.perf_counter())
    count = _sample(
        "qc_worker_pump_round_seconds_count",
        {"worker_id": "99001", "pump": "paper"},
    )
    assert count is not None and count >= 1.0


def test_inc_sync_failure_increments():
    labels = {"worker_id": "99002", "kind": "live"}
    before = _sample("qc_worker_sync_failures_total", labels) or 0.0
    obs.inc_sync_failure(99002, "live")
    assert (_sample("qc_worker_sync_failures_total", labels) or 0.0) == before + 1.0


def test_inc_worker_restart_increments():
    labels = {"worker_id": "99003"}
    before = _sample("qc_worker_restarts_total", labels) or 0.0
    obs.inc_worker_restart(99003)
    assert (_sample("qc_worker_restarts_total", labels) or 0.0) == before + 1.0


def test_queue_depth_gauge_registered():
    """gauge 注册即存在；抓取回调懒加载 worker.state（顶部无 DB 链，可导）"""
    assert REGISTRY.get_sample_value("qc_worker_queue_depth") is not None
