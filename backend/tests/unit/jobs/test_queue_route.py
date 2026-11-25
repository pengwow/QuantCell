"""`GET /api/v1/jobs/queue` 聚合逻辑与响应契约。"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from jobs import routes


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(routes.router)
    return TestClient(app)


def _counts(queued: int, running: int, cores: list[int], max_pending: int = 32) -> dict:
    return {
        "queued": queued,
        "running": running,
        "succeeded": 0,
        "failed": 0,
        "cancelled": 0,
        "interrupted": 0,
        "max_workers": len(cores) or 1,
        "cores": cores,
        "max_pending": max_pending,
    }


def test_queue_snapshot_aggregates_existing_pools(monkeypatch):
    monkeypatch.setattr(routes, "pool_enabled", lambda: True)
    monkeypatch.setattr(
        routes.backtest_job_manager, "pool_status", lambda: _counts(queued=3, running=1, cores=[4, 5], max_pending=3)
    )
    monkeypatch.setattr(routes, "rl_pool_status", lambda: _counts(queued=0, running=1, cores=[5, 6]))
    monkeypatch.setattr(routes, "hpo_pool_status", lambda: None)

    data = routes.queue_snapshot()

    assert data["queued"] == 3
    assert data["running"] == 2
    assert data["cores"] == 3  # [4,5] ∪ [5,6]
    # 回测池排队 3/3 已满 → 阻断原因里必须点名
    assert any("回测队列已满" in reason for reason in data["blocked"])
    assert data["pools"]["hpo_trial"]["created"] is False
    assert data["pools"]["backtest"]["blocked"] is True


def test_queue_snapshot_reports_disabled_pool_without_creating(monkeypatch):
    monkeypatch.setattr(routes, "pool_enabled", lambda: False)
    monkeypatch.setattr(routes.backtest_job_manager, "pool_status", lambda: None)
    monkeypatch.setattr(routes, "rl_pool_status", lambda: None)
    monkeypatch.setattr(routes, "hpo_pool_status", lambda: None)
    monkeypatch.setattr(routes, "resolve_cores", lambda: [8, 9])

    data = routes.queue_snapshot()

    assert (data["queued"], data["running"]) == (0, 0)
    assert data["cores"] == 2  # 未建池时按配置推算已绑核数
    assert data["blocked"][0].startswith("进程池未启用")


def test_queue_route_returns_api_response(monkeypatch):
    monkeypatch.setattr(routes, "pool_enabled", lambda: True)
    monkeypatch.setattr(routes.backtest_job_manager, "pool_status", lambda: None)
    monkeypatch.setattr(routes, "rl_pool_status", lambda: None)
    monkeypatch.setattr(routes, "hpo_pool_status", lambda: None)
    monkeypatch.setattr(routes, "resolve_cores", lambda: [])

    response = _client().get("/api/v1/jobs/queue")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["queued"] == 0
    assert body["data"]["running"] == 0
    assert body["data"]["cores"] == 0
    assert body["data"]["blocked"] == []
