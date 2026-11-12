"""能力开关 capability flags 单测（P2-02）

覆盖：内置默认值契约、env > config.toml > 默认值的覆盖优先级、
require_capability 403 结构（code + capability 定位字段）、实盘闸门
（live/testnet 拦、paper 放行）、capabilities 端点 envelope、
worker 创建/启动/批量启动三处闸门的真实接线（装饰器透传 403）。
"""

from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.testclient import TestClient

from api.capabilities_routes import router as capabilities_router
from config import capabilities
from config.capabilities import (
    Capability,
    get_capabilities,
    is_enabled,
    require_capability,
    require_live_trading,
)
from worker import routes as worker_routes
from worker.schemas import BatchOperationRequest, TradingConfig, WorkerCreate

# ---------- 内置默认值与覆盖优先级 ----------


def test_builtin_defaults(monkeypatch):
    """默认与单机现状兼容：实盘/Agent 开启；mcp_server 未实现（P2-04 预留）恒关"""
    # patch get_flag 透传 default：隔离真实 config.toml 的实例值，只验默认值契约
    monkeypatch.setattr(capabilities, "get_flag", lambda key, default: default)
    assert get_capabilities() == {
        "live_trading": True,
        "agent_gateway": True,
        "mcp_server": False,
    }


def test_env_override_wins(monkeypatch):
    """env 优先于 config.toml（当前文件值 live_trading=true，env=false 必须生效）"""
    monkeypatch.setenv("QUANTCELL_CAPABILITY_LIVE_TRADING", "false")
    monkeypatch.setattr(capabilities, "get_flag", lambda key, default: default)
    assert is_enabled(Capability.LIVE_TRADING) is False


def test_env_invalid_value_falls_back_to_config(monkeypatch):
    """非法 env 值忽略并回退配置通道，不抛异常"""
    monkeypatch.setenv("QUANTCELL_CAPABILITY_AGENT_GATEWAY", "maybe")
    monkeypatch.setattr(capabilities, "get_flag", lambda key, default: default)
    assert is_enabled(Capability.AGENT_GATEWAY) is True


def test_config_flag_override(monkeypatch):
    """config.toml [capabilities] 分组生效（get_flag 返回 false 时覆盖内置 true）"""
    monkeypatch.setattr(capabilities, "get_flag", lambda key, default: False)
    assert is_enabled(Capability.LIVE_TRADING) is False


# ---------- 守卫依赖 ----------


def test_require_capability_403_structure(monkeypatch):
    """403 detail：code 供机器判定，data.capability 供前端定位降级文案"""
    monkeypatch.setattr(capabilities, "is_enabled", lambda cap: False)
    dep = require_capability(Capability.AGENT_GATEWAY)
    with pytest.raises(HTTPException) as ei:
        dep()
    assert ei.value.status_code == 403
    assert ei.value.detail["code"] == 403
    assert ei.value.detail["data"] == {"capability": "agent_gateway", "enabled": False}


def test_require_capability_passes(monkeypatch):
    monkeypatch.setattr(capabilities, "is_enabled", lambda cap: True)
    require_capability(Capability.AGENT_GATEWAY)()  # 不抛即通过


@pytest.mark.parametrize("mode", ["live", "testnet"])
def test_live_modes_blocked_when_capability_off(monkeypatch, mode):
    """实盘域（含 testnet：strategy_manager 中其 run_mode 同为 live）需要能力"""
    monkeypatch.setattr(capabilities, "is_enabled", lambda cap: False)
    with pytest.raises(HTTPException) as ei:
        require_live_trading(mode)
    assert ei.value.status_code == 403
    assert ei.value.detail["data"]["capability"] == "live_trading"


def test_paper_bypasses_live_gate(monkeypatch):
    """paper 纯模拟，能力关闭也不拦"""
    monkeypatch.setattr(capabilities, "is_enabled", lambda cap: False)
    require_live_trading("paper")  # 不抛即通过


def test_live_allowed_when_capability_on(monkeypatch):
    monkeypatch.setattr(capabilities, "is_enabled", lambda cap: True)
    require_live_trading("live")  # 不抛即通过


# ---------- capabilities 端点 ----------


def test_capabilities_endpoint_envelope(monkeypatch):
    monkeypatch.setattr(capabilities, "get_flag", lambda key, default: default)
    app = FastAPI()
    app.include_router(capabilities_router)
    with TestClient(app) as client:
        resp = client.get("/api/v1/capabilities")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"] == {"live_trading": True, "agent_gateway": True, "mcp_server": False}


# ---------- worker 路由接线（创建 / 启动 / 批量启动闸门） ----------


def _fake_worker(mode: str):
    return SimpleNamespace(get_trading_config_dict=lambda: {"trading_mode": mode})


def _live_enabled(monkeypatch, enabled: bool):
    monkeypatch.setattr(capabilities, "is_enabled", lambda cap: enabled)


@pytest.fixture()
def capability_off(monkeypatch):
    _live_enabled(monkeypatch, False)


async def test_create_live_worker_403_when_disabled(capability_off):
    request = WorkerCreate(name="t", trading_config=TradingConfig(trading_mode="live"))
    with pytest.raises(HTTPException) as ei:
        await worker_routes.create_worker(request, db=None, current_user={"user_id": "1"})
    assert ei.value.status_code == 403


async def test_create_paper_worker_reaches_service_when_disabled(capability_off, monkeypatch):
    """能力关但 paper 配置必须正常创建（闸门只拦实盘域）"""
    calls: list[dict] = []

    async def _create(data):
        calls.append(data)
        return {"id": 1}

    monkeypatch.setattr(worker_routes.worker_core_service, "async_create_worker", _create)
    request = WorkerCreate(name="t", trading_config=TradingConfig(trading_mode="paper"))
    result = await worker_routes.create_worker(request, db=None, current_user={"user_id": "1"})
    assert result.code == 0
    assert calls  # create 被真实调用


async def test_start_live_worker_403_when_disabled(capability_off, monkeypatch):
    monkeypatch.setattr(worker_routes.crud, "get_worker", lambda db, wid: _fake_worker("live"))

    async def _fail_start(worker_id):
        raise AssertionError("live worker 不应在能力关闭时进入启动服务")

    monkeypatch.setattr(worker_routes.worker_core_service, "async_start_worker", _fail_start)
    with pytest.raises(HTTPException) as ei:
        await worker_routes.start_worker(1, BackgroundTasks(), db=None, current_user={"user_id": "1"})
    assert ei.value.status_code == 403


async def test_start_paper_worker_reaches_service_when_disabled(capability_off, monkeypatch):
    monkeypatch.setattr(worker_routes.crud, "get_worker", lambda db, wid: _fake_worker("paper"))

    async def _start(worker_id):
        return {"worker_id": worker_id, "status": "starting"}

    async def _state(worker_id):
        return None

    monkeypatch.setattr(worker_routes.worker_core_service, "async_start_worker", _start)
    monkeypatch.setattr(worker_routes.worker_state_manager, "get_state", _state)
    result = await worker_routes.start_worker(1, BackgroundTasks(), db=None, current_user={"user_id": "1"})
    assert result.data["status"] == "starting"


@pytest.mark.parametrize("operation", ["start", "restart"])
async def test_batch_live_worker_403_when_disabled(capability_off, monkeypatch, operation):
    monkeypatch.setattr(worker_routes.crud, "get_worker", lambda db, wid: _fake_worker("testnet"))

    async def _fail_batch(ids, op):
        raise AssertionError(f"operation={op} 不应在能力关闭时进入批量服务")

    monkeypatch.setattr(worker_routes.worker_core_service, "async_batch_operation", _fail_batch)
    request = BatchOperationRequest(worker_ids=[1, 2], operation=operation)
    with pytest.raises(HTTPException) as ei:
        await worker_routes.batch_operation(request, BackgroundTasks(), db=None, current_user={"user_id": "1"})
    assert ei.value.status_code == 403


async def test_batch_stop_not_gated_when_disabled(capability_off, monkeypatch):
    """stop 是安全方向操作，能力关闭时仍可执行"""
    calls: list[tuple] = []

    async def _batch(ids, op):
        calls.append((ids, op))
        return {"success": ids, "failed": []}

    monkeypatch.setattr(worker_routes.worker_core_service, "async_batch_operation", _batch)
    request = BatchOperationRequest(worker_ids=[1], operation="stop")
    result = await worker_routes.batch_operation(request, BackgroundTasks(), db=None, current_user={"user_id": "1"})
    assert calls == [([1], "stop")]
    assert result.code == 0
