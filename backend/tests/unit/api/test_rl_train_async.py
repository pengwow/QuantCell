"""RL 训练任务化 API 契约：async 提交 / 快照 / SSE / 取消。

真实训练被 patch 成假函数（`services.rl_task_runner._default_train`），只验证
HTTP 契约与 runner 的接线，不起 SB3。
"""

from __future__ import annotations

import json
import threading
import time
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services import rl_task_runner as runner


@pytest.fixture(autouse=True)
def _debug_mode(monkeypatch):
    monkeypatch.setenv("DEBUG", "true")


@pytest.fixture(autouse=True)
def _clean_registry():
    runner.reset_tasks()
    yield
    runner.reset_tasks()
    assert runner._worker_lock.acquire(timeout=5), "上一用例的训练线程未退出"
    runner._worker_lock.release()


def _make_client() -> TestClient:
    from api.rl_routes import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _wait(predicate, timeout: float = 5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.01)
    raise AssertionError("等待超时")


def _fast_train(config, reporter):
    reporter.state(stage="learning", progress=0.5, message="假训练")
    reporter.log("fake log line")
    return SimpleNamespace(model_id="fake_model", model_path="/tmp/models/fake.zip", metrics={})


def _blocking_train(config, reporter):
    for _ in range(400):
        reporter.check_cancel()
        reporter.state(stage="learning", progress=0.5, message="训练中")
        time.sleep(0.005)
    return SimpleNamespace(model_id="never", model_path=None, metrics={})


def test_async_train_returns_202_queued(monkeypatch):
    monkeypatch.setattr(runner, "_default_train", _fast_train)
    client = _make_client()

    resp = client.post("/api/v1/rl/train/async", json={"symbol": "BTCUSDT", "total_timesteps": 64})

    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "queued"
    assert body["task_id"].startswith("rltrain_")
    assert set(body) == {"task_id", "status"}


def test_async_train_missing_symbol_returns_422():
    client = _make_client()
    resp = client.post("/api/v1/rl/train/async", json={"algorithm": "ppo"})
    assert resp.status_code == 422


def test_task_snapshot_contract(monkeypatch):
    monkeypatch.setattr(runner, "_default_train", _fast_train)
    client = _make_client()
    task_id = client.post("/api/v1/rl/train/async", json={"symbol": "BTCUSDT"}).json()["task_id"]

    snap = _wait(lambda: (body := client.get(f"/api/v1/rl/train/{task_id}").json())["status"] == "done" and body)
    assert snap["task_id"] == task_id
    assert snap["stage"] == "done"
    assert snap["progress"] == 1.0
    assert snap["model_path"] == "/tmp/models/fake.zip"
    assert snap["meta_path"] == "/tmp/models/fake.zip.meta.json"
    assert snap["error"] is None
    assert isinstance(snap["elapsed_ms"], int)


def test_task_snapshot_unknown_returns_404():
    client = _make_client()
    assert client.get("/api/v1/rl/train/rltrain_nope").status_code == 404


def test_events_stream_yields_state_and_log_then_closes(monkeypatch):
    monkeypatch.setattr(runner, "_default_train", _fast_train)
    client = _make_client()
    task_id = client.post("/api/v1/rl/train/async", json={"symbol": "BTCUSDT"}).json()["task_id"]

    resp = client.get(f"/api/v1/rl/train/{task_id}/events")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    body = resp.text
    state_payloads = [
        json.loads(line[len("data: ") :])
        for line in body.splitlines()
        if line.startswith("data: ") and '{"task_id"' in line
    ]
    assert state_payloads
    assert state_payloads[-1]["status"] == "done"  # 终态后连接关闭
    assert "event: log" in body
    assert "fake log line" in body


def test_events_stream_reports_running_state(monkeypatch):
    gate = threading.Event()

    def gated(config, reporter):
        reporter.state(stage="learning", progress=0.4, message="训练中")
        reporter.log("gated line")
        gate.wait(5)
        return SimpleNamespace(model_id="g", model_path=None, metrics={})

    monkeypatch.setattr(runner, "_default_train", gated)
    client = _make_client()
    task_id = client.post("/api/v1/rl/train/async", json={"symbol": "BTCUSDT"}).json()["task_id"]

    threading.Timer(0.3, gate.set).start()
    resp = client.get(f"/api/v1/rl/train/{task_id}/events")

    assert resp.status_code == 200
    assert '"status": "running"' in resp.text  # 中途快照真的流出来了
    assert "gated line" in resp.text
    assert '"status": "done"' in resp.text


def test_cancel_running_task_returns_accepted(monkeypatch):
    monkeypatch.setattr(runner, "_default_train", _blocking_train)
    client = _make_client()
    task_id = client.post("/api/v1/rl/train/async", json={"symbol": "BTCUSDT"}).json()["task_id"]

    resp = client.post(f"/api/v1/rl/train/{task_id}/cancel")
    assert resp.status_code == 200
    assert resp.json() == {"accepted": True}

    snap = _wait(lambda: (body := client.get(f"/api/v1/rl/train/{task_id}").json())["status"] == "cancelled" and body)
    assert snap["message"] == "训练已取消"


def test_cancel_finished_task_returns_409(monkeypatch):
    monkeypatch.setattr(runner, "_default_train", _fast_train)
    client = _make_client()
    task_id = client.post("/api/v1/rl/train/async", json={"symbol": "BTCUSDT"}).json()["task_id"]
    _wait(lambda: client.get(f"/api/v1/rl/train/{task_id}").json()["status"] == "done")

    resp = client.post(f"/api/v1/rl/train/{task_id}/cancel")
    assert resp.status_code == 409


def test_cancel_unknown_task_returns_404():
    client = _make_client()
    assert client.post("/api/v1/rl/train/rltrain_nope/cancel").status_code == 404


def test_sync_train_endpoint_unchanged(monkeypatch):
    """同步 /train 契约不动（ModelHub 在用）：仍返回 ApiResponse + completed。"""
    from unittest.mock import MagicMock, patch

    client = _make_client()
    mock_result = MagicMock()
    mock_result.model_id = "m1"
    mock_result.metrics = {"steps": 10}
    mock_result.walk_forward = None

    with patch("services.rl_service.RLService") as MockSvc:
        MockSvc.return_value.train.return_value = mock_result
        resp = client.post("/api/v1/rl/train", json={"symbol": "BTCUSDT"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["status"] == "completed"
    assert body["data"]["model_id"] == "m1"
