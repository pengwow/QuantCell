"""GET /api/v1/workers 列表实时状态覆盖的契约测试。

核心行为：get_all_states 只返回已水合的缓存记录；后端重启后缓存为空，
列表必须回退到 get_state（惰性水合）以保证与 GET /{id}/state 口径一致，
而不是展示 DB 中的残留中间状态（如 interrupted）。
"""

from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from utils.auth import get_current_user
from worker import routes
from worker.dependencies import get_db_session
from worker.worker_state import WorkerStateRecord


@pytest.fixture()
def client(monkeypatch):
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[get_db_session] = lambda: None
    app.dependency_overrides[get_current_user] = lambda: {"sub": "test"}
    return TestClient(app)


def _state(worker_id, status):
    return WorkerStateRecord(
        worker_id=worker_id,
        status=status,
        pid=None,
        started_at=None,
        stopped_at=None,
        updated_at=datetime.now(),
    )


def test_list_overrides_stale_db_status_via_hydration(client, monkeypatch):
    """重启后缓存为空：DB 残留 interrupted 必须被水合后的 stopped 覆盖。"""

    async def _list_workers(**kw):
        return {"items": [{"id": 4, "status": "interrupted"}], "total": 1}

    async def _empty_cache():
        return {}

    async def _hydrated_state(worker_id):
        return _state(worker_id, "stopped")

    monkeypatch.setattr(routes.worker_core_service, "async_list_workers", _list_workers)
    monkeypatch.setattr(routes.worker_state_manager, "get_all_states", _empty_cache)
    monkeypatch.setattr(routes.worker_state_manager, "get_state", _hydrated_state)

    r = client.get("/api/v1/workers").json()
    item = r["data"]["items"][0]
    assert item["status"] == "stopped"  # 与 GET /4/state 口径一致
    assert item["_status"] == "stopped"
    assert "_updated_at" in item


def test_list_uses_cached_state_first(client, monkeypatch):
    """缓存命中时不触发额外的 get_state 调用。"""

    async def _fail_get_state(worker_id):
        raise AssertionError("缓存命中时不应回退到 get_state")

    async def _list_workers(**kw):
        return {"items": [{"id": 4, "status": "running"}], "total": 1}

    async def _cached_cache():
        return {4: _state(4, "running")}

    monkeypatch.setattr(routes.worker_core_service, "async_list_workers", _list_workers)
    monkeypatch.setattr(routes.worker_state_manager, "get_all_states", _cached_cache)
    monkeypatch.setattr(routes.worker_state_manager, "get_state", _fail_get_state)

    r = client.get("/api/v1/workers").json()
    item = r["data"]["items"][0]
    assert item["status"] == "running"
    assert item["_pid"] is None
