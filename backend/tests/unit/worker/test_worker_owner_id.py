"""P1-07 工人属地：owner_id 落库与契约测试

覆盖：
- crud.create_worker 将路由层注入的 owner_id 持久化（迁移 34 / create_all 双通道）
- Worker.to_dict 输出 owner_id（前端与后续归属过滤消费）
- WorkerCreate 显式声明 owner_id：extra="forbid" 下服务端注入合法，
  JWT sub 常见的数字字符串经 pydantic lax 模式强转为 int
"""

import pytest

from worker import crud, schemas


def _worker_payload(**overrides):
    payload = {
        "name": "owner-test",
        "strategy_id": 1,
        "trading_config": {
            "exchange": "binance",
            "symbols_config": {"type": "symbols", "symbols": ["BTCUSDT"]},
            "timeframe": "1h",
            "market_type": "spot",
            "trading_mode": "paper",
        },
    }
    payload.update(overrides)
    return payload


class TestWorkerOwnerId:
    def test_create_persists_owner_id(self, db_session):
        """路由层注入的 owner_id 应完整落库并以 to_dict 输出"""
        worker = crud.create_worker(db_session, schemas.WorkerCreate(**_worker_payload(owner_id=42)))
        db_session.refresh(worker)
        assert worker.owner_id == 42
        assert worker.to_dict()["owner_id"] == 42

    def test_owner_id_defaults_none(self, db_session):
        """未登录/历史数据 owner_id 为 None（无归属，单用户语义不变）"""
        worker = crud.create_worker(db_session, schemas.WorkerCreate(**_worker_payload()))
        db_session.refresh(worker)
        assert worker.owner_id is None
        assert worker.to_dict()["owner_id"] is None

    def test_schema_accepts_numeric_string_sub(self):
        """JWT sub 为数字字符串时 schema lax 强转 int；非数字由路由层 suppress 归 None"""
        data = schemas.WorkerCreate(**_worker_payload(owner_id="7"))
        assert data.owner_id == 7


class TestWorkerListOwnerFilter:
    def test_owner_filter_returns_only_own(self, db_session):
        """非特权用户列表只返回自己的 worker（跨用户可见缺陷的回归锁）"""
        crud.create_worker(db_session, schemas.WorkerCreate(**_worker_payload(name="w-a", owner_id=42)))
        crud.create_worker(db_session, schemas.WorkerCreate(**_worker_payload(name="w-b", owner_id=7)))
        crud.create_worker(db_session, schemas.WorkerCreate(**_worker_payload(name="w-c")))

        mine, total = crud.get_workers(db_session, owner_id=42)
        assert total == 1
        assert {w.owner_id for w in mine} == {42}

        _workers, total_all = crud.get_workers(db_session)
        assert total_all == 3  # None = 不过滤（admin/agent 特权路径）

    def test_owner_filter_excludes_unowned(self, db_session):
        """无主 worker 不对普通用户可见（历史数据由回填脚本处理）"""
        crud.create_worker(db_session, schemas.WorkerCreate(**_worker_payload(name="legacy")))
        mine, total = crud.get_workers(db_session, owner_id=42)
        assert total == 0 and mine == []


class TestWorkerListRouteOwnerFilter:
    """路由层归属过滤契约（P0 跨用户可见修复）。

    三个口径：human 只看自己；admin/agent 免过滤；鉴权关闭（debug/桌面）
    current_user 为 {}，单机模式不过滤——最后这条曾把列表整个清空过。
    """

    @pytest.fixture()
    def route_client(self, monkeypatch):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from utils.auth import get_current_user
        from worker import routes
        from worker.dependencies import get_db_session

        captured: dict = {}

        async def _list_workers(**kw):
            captured["owner_id"] = kw.get("owner_id")
            return {"items": [], "total": 0}

        monkeypatch.setattr(routes.worker_core_service, "async_list_workers", _list_workers)

        app = FastAPI()
        app.include_router(routes.router)
        app.dependency_overrides[get_db_session] = lambda: None
        client = TestClient(app)
        client.captured = captured
        return client

    def _set_user(self, client, user: dict):
        from utils.auth import get_current_user

        client.app.dependency_overrides[get_current_user] = lambda: user

    def test_human_sees_only_own(self, route_client):
        self._set_user(route_client, {"user_id": "11", "role": "user", "sub": "11"})
        route_client.get("/api/v1/workers")
        assert route_client.captured["owner_id"] == 11

    def test_admin_and_agent_exempt(self, route_client):
        self._set_user(route_client, {"user_id": "1", "role": "admin"})
        route_client.get("/api/v1/workers")
        assert route_client.captured["owner_id"] is None

        self._set_user(route_client, {"role": "agent", "sub": "agent_token:5"})
        route_client.get("/api/v1/workers")
        assert route_client.captured["owner_id"] is None

    def test_auth_off_means_single_user_no_filter(self, route_client):
        """鉴权关闭时 current_user={}，必须放行全量（单机模式语义）"""
        self._set_user(route_client, {})
        route_client.get("/api/v1/workers")
        assert route_client.captured["owner_id"] is None

    def test_unparseable_user_gets_nothing(self, route_client):
        self._set_user(route_client, {"role": "user", "user_id": "guest_x"})
        route_client.get("/api/v1/workers")
        assert route_client.captured["owner_id"] == -1
