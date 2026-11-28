"""启动链路多标的固化公约测试（spec §4 + 2026-11-28 现价固化）。

只锁固化公约（不测启动编排本身）：
1. per-symbol 分份：每个标的一份完整固化 entry，preview 逐标的独立调用；
2. ref 缺失（None / <=0）→ pending 占位（None），不阻塞其他标的（Partial 固化）；
3. preview 失败（PlanPreviewError）→ 不炸启动链路，该标的 pending；
4. 非计划策略（has_price_plan False）→ 不写库；
5. fixed_at 为 9 位纳秒 ISO 时间戳（项目时间戳规范）。

现价自动固化（2026-11-28）：
6. 无 ref_prices 启动 → 一律用启动实时价重锚（条目 fixed 且 ref=现价、plan 非空）；
7. 现价取不到 → 该标的回 pending 占位，不阻断启动；
8. 弹窗显式传价不被现价重锚触碰；
9. 非计划策略不取现价、不写库。

详情接口能力位：GET /workers/{id}/state 的 strategy_info.has_price_plan True/False
两态，registry 探测失败回退 False 不炸。

strategy 服务 / crud 写入 / 现价源全部 monkeypatch（真行情服务的异常面与限速不进公约测试）。
"""

import asyncio
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from strategy.service import PlanPreviewError
from utils.auth import get_current_user
from worker.dependencies import get_db_session
from worker.routes import router
from worker.strategy_manager import StrategyManager
from worker.worker_state import worker_state_manager


class _StubSvc:
    """计划服务 stub：has_price_plan 可控；preview 返回含 ref 身份的 dict"""

    def __init__(self, supported=True, error=None):
        self.supported = supported
        self.error = error
        self.previews = []  # (name, params, ref_price) 记录，供「逐标的独立调用」断言

    def has_price_plan(self, name):
        return self.supported

    def preview_price_plan(self, name, params=None, ref_price=None):
        self.previews.append((name, params, ref_price))
        if self.error is not None:
            raise self.error
        return {"ref_price": ref_price}  # 每次新 dict，身份互不相同


@pytest.fixture
def svc(monkeypatch):
    """_persist_worker_price_plan 经 strategy.routes.get_strategy_service 取服务
    （函数内 import），patch 模块属性即可生效"""
    stub = _StubSvc()
    monkeypatch.setattr("strategy.routes.get_strategy_service", lambda: stub)
    return stub


@pytest.fixture
def saved(monkeypatch):
    calls = []

    def _fake_save(worker_id, plans):
        calls.append((int(worker_id), dict(plans)))
        return True

    monkeypatch.setattr("worker.strategy_manager.crud.save_worker_price_plans", _fake_save)
    return calls


@pytest.fixture
def manager():
    return StrategyManager()


NS_TS = re.compile(r"\.\d{9}")


def test_persist_per_symbol_entries(manager, svc, saved):
    """两个 ref 有效标的：每份 fixed entry 完整（symbol/state/ref_price/plan/fixed_at），
    plan 是逐标的独立 preview 产物（身份互不相同）"""
    manager._persist_worker_price_plan(1, "grid", {"levels": 20}, {"BTCUSDT": 100.0, "ETHUSDT": 2000.0})

    assert len(saved) == 1
    wid, plans = saved[0]
    assert wid == 1
    assert set(plans.keys()) == {"BTCUSDT", "ETHUSDT"}
    for sym, ref in (("BTCUSDT", 100.0), ("ETHUSDT", 2000.0)):
        entry = plans[sym]
        assert entry["symbol"] == sym
        assert entry["state"] == "fixed"
        assert entry["ref_price"] == ref
        assert entry["plan"] == {"ref_price": ref}
    assert plans["BTCUSDT"]["plan"] is not plans["ETHUSDT"]["plan"]  # 逐标的独立 preview
    assert svc.previews == [("grid", {"levels": 20}, 100.0), ("grid", {"levels": 20}, 2000.0)]
    # 顺序按 ref_prices 输入序
    assert list(plans.keys()) == ["BTCUSDT", "ETHUSDT"]


def test_persist_fixed_at_nanoseconds(manager, svc, saved):
    """fixed_at 是 9 位小数的 ISO 时间戳（纳秒规范，补尾零）"""
    manager._persist_worker_price_plan(1, "grid", {}, {"BTCUSDT": 100.0})
    _, plans = saved[0]
    assert NS_TS.search(plans["BTCUSDT"]["fixed_at"])


def test_persist_mixed_fixed_and_pending(manager, svc, saved):
    """部分标的有效：有价固化、无价/零/负价 pending"""
    manager._persist_worker_price_plan(1, "grid", {}, {"BTCUSDT": 100.0, "ETHUSDT": None, "LTCUSDT": 0, "XRPUSDT": -5})

    _, plans = saved[0]
    assert plans["BTCUSDT"]["state"] == "fixed"
    assert plans["ETHUSDT"] is None
    assert plans["LTCUSDT"] is None
    assert plans["XRPUSDT"] is None
    # 只有 BTCUSDT 触发 preview
    assert [p[2] for p in svc.previews] == [100.0]


def test_persist_preview_error_falls_to_pending(manager, svc, saved):
    """preview 抛 PlanPreviewError：该标的 pending，不炸启动链路"""
    svc.error = PlanPreviewError("REF_PRICE_REQUIRED", "缺参考价")

    manager._persist_worker_price_plan(1, "grid", {}, {"BTCUSDT": 100.0, "ETHUSDT": 2000.0})

    _, plans = saved[0]
    assert plans == {"BTCUSDT": None, "ETHUSDT": None}


def test_persist_no_price_plan_skips_db_write(manager, svc, saved):
    """非计划策略：早退不写库（避免无谓 config 写入）"""
    svc.supported = False

    manager._persist_worker_price_plan(1, "dual_ma", {}, {"BTCUSDT": None})

    assert saved == []
    assert svc.previews == []


def test_persist_empty_ref_prices_skips_db_write(manager, svc, saved):
    """ref_prices 为空：跳过写库（避免把旧固化清成 {"plans": {}}）"""
    manager._persist_worker_price_plan(1, "grid", {}, {})
    assert saved == []


def test_persist_resolves_per_symbol_params(manager, svc, saved):
    """D1：固化按标的合并参数——BTC 有覆盖、ETH 无覆盖用公共参数（resolver 唯一出口）"""
    by_symbol = {"BTCUSDT": {"lower": 100.0}, "ETHUSDT": {"lower": None}}  # None 视同未覆盖
    manager._persist_worker_price_plan(1, "grid", {"levels": 20}, {"BTCUSDT": 50000.0, "ETHUSDT": 2000.0}, by_symbol)
    assert svc.previews[0][1] == {"levels": 20, "lower": 100.0}  # BTC：公共 + 覆盖
    assert svc.previews[1][1] == {"levels": 20}  # ETH：仅公共


# ---------------------------------------------------------------------------
# 现价自动固化（2026-11-28）：ref 缺失的标的一律用启动实时价重锚；
# 取价失败 → pending 占位不阻断；弹窗显式传价不被触碰。
# ---------------------------------------------------------------------------


class _SentinelAfterPlan(Exception):
    """_assemble_rule_paper_driver 的断流标记：固化之后的 driver 装配不属于本公约"""


class _PlanStrategyRow:
    """Strategy 行 stub（真实 grid 模块不会被本组测试装载）"""

    id = 1
    name = "grid"
    parameters = None
    strategy_type = "rule"
    description = ""
    version = "1"


class _StubWorkerRow:
    def __init__(self, symbols=("BTCUSDT",)):
        self.id = 1
        self.name = "w"
        self.strategy_id = 1
        self.strategy = _PlanStrategyRow()
        self._symbols = list(symbols)

    def get_trading_config_dict(self):
        return {"interval": "1h", "market_type": "spot", "trading_mode": "paper"}

    def get_symbols(self):
        return list(self._symbols)

    def get_config_dict(self):
        return {}


@pytest.fixture
def spot(monkeypatch):
    """假现价源：可控行情（price 可改 / error 注入 / 调用记录），不真连网"""
    holder = SimpleNamespace(price=666.5, error=None, calls=[])

    async def _fake(symbol, market_type="spot", exchange="binance"):
        holder.calls.append((symbol, market_type, exchange))
        if holder.error is not None:
            raise holder.error
        return {"symbol": symbol, "price": holder.price, "ts": "t"}

    monkeypatch.setattr("worker.strategy_manager.fetch_latest_price", _fake)
    return holder


def _run_start_to_plan(manager, monkeypatch, worker, ref_price=None):
    """把 _do_start_strategy 跑过价格计划固化、在 driver 装配前断流。

    registry / 策略装载 / driver 装配打桩；断流位置在固化之后——启动链路能
    抛出 _Sentinel 即视为「取价失败等异常面没有阻断启动」。
    """
    monkeypatch.setattr(
        "worker.state.strategy_registry",
        SimpleNamespace(get=lambda wid: SimpleNamespace(is_running=False)),
    )
    monkeypatch.setattr(
        "backtest.strategy_loader_service.StrategyLoaderService.load_strategy",
        staticmethod(lambda **kw: object()),
    )

    def _cut(*args, **kwargs):
        raise _SentinelAfterPlan()

    monkeypatch.setattr(manager, "_assemble_rule_paper_driver", _cut)

    with pytest.raises(_SentinelAfterPlan):
        asyncio.run(manager._do_start_strategy(worker.id, worker, ref_price=ref_price))


def test_startup_no_refs_fixed_with_spot(manager, svc, saved, spot, monkeypatch):
    """无 ref_prices 启动（重启恢复 / restart / 批量）：条目 fixed 且 ref=现价、plan 非空"""
    _run_start_to_plan(manager, monkeypatch, _StubWorkerRow())
    assert spot.calls == [("BTCUSDT", "spot", "binance")]
    _, plans = saved[0]
    entry = plans["BTCUSDT"]
    assert entry["state"] == "fixed"
    assert entry["ref_price"] == 666.5
    assert entry["plan"]


def test_startup_spot_failure_pending_without_block(manager, svc, saved, spot, monkeypatch):
    """取价失败（网络 / 上市新币）：该标的回 pending 占位，启动链路不被阻断"""
    spot.error = RuntimeError("network unreachable")
    _run_start_to_plan(manager, monkeypatch, _StubWorkerRow())
    _, plans = saved[0]
    assert plans["BTCUSDT"] is None


def test_startup_popup_refs_win_over_spot(manager, svc, saved, spot, monkeypatch):
    """弹窗逐标的传价：显式价不被现价重锚触碰（现价源零调用）"""
    _run_start_to_plan(manager, monkeypatch, _StubWorkerRow(), ref_price={"BTCUSDT": 100.0})
    assert spot.calls == []
    _, plans = saved[0]
    assert plans["BTCUSDT"]["ref_price"] == 100.0


def test_startup_scalar_ref_reanchors_rest(manager, svc, saved, spot, monkeypatch):
    """标量 ref：首标用显式价，其余标的一律现价重锚（不再落 pending）"""
    _run_start_to_plan(manager, monkeypatch, _StubWorkerRow(symbols=["BTCUSDT", "ETHUSDT"]), ref_price=100.0)
    _, plans = saved[0]
    assert plans["BTCUSDT"]["ref_price"] == 100.0
    assert plans["ETHUSDT"]["state"] == "fixed"
    assert plans["ETHUSDT"]["ref_price"] == 666.5


def test_anchor_normalizes_market_type_aliases(manager, spot):
    """market_type 别名归一（trading_config 的 future / RL 的 swap → ticker 端点的 futures）"""
    ref = {"BTCUSDT": None}
    asyncio.run(manager._anchor_missing_refs_with_spot(1, "grid", ref, "binance", "future"))
    assert spot.calls == [("BTCUSDT", "futures", "binance")]
    assert ref == {"BTCUSDT": 666.5}


def test_startup_non_plan_strategy_skips_spot(manager, svc, saved, spot, monkeypatch):
    """无计划能力策略：不取现价、不写库（省一次无谓的行情回源）"""
    svc.supported = False
    _run_start_to_plan(manager, monkeypatch, _StubWorkerRow())
    assert spot.calls == []
    assert saved == []


# ---------------------------------------------------------------------------
# 详情接口能力位：GET /workers/{id}/state → strategy_info.has_price_plan
# ---------------------------------------------------------------------------


class _StateRow:
    status = "stopped"

    def to_dict(self):
        return {"worker_id": 1, "status": "stopped"}


class _DetailStrategyRow:
    id = 30
    name = "grid"
    description = ""
    strategy_type = "rule"
    version = "1"


class _DetailWorkerRow:
    id = 1
    name = "w"
    strategy_id = 30
    strategy = _DetailStrategyRow()

    def get_trading_config_dict(self):
        return {"exchange": "binance", "market_type": "spot", "trading_mode": "paper"}

    def get_symbols(self):
        return ["BTCUSDT"]

    def get_interval(self):
        return "1h"


@pytest.fixture()
def detail_client(monkeypatch):
    monkeypatch.setattr("worker.crud.get_worker", lambda db, wid: _DetailWorkerRow())
    monkeypatch.setattr(worker_state_manager, "get_state", AsyncMock(return_value=_StateRow()))
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db_session] = lambda: None
    app.dependency_overrides[get_current_user] = lambda: {"sub": "t"}
    return TestClient(app)


def test_state_strategy_info_has_price_plan_true(detail_client, svc):
    data = detail_client.get("/api/v1/workers/1/state").json()["data"]
    assert data["strategy_info"]["has_price_plan"] is True


def test_state_strategy_info_has_price_plan_false(detail_client, svc):
    svc.supported = False
    data = detail_client.get("/api/v1/workers/1/state").json()["data"]
    assert data["strategy_info"]["has_price_plan"] is False


def test_state_has_price_plan_false_when_probe_fails(detail_client, monkeypatch):
    """registry 读不到（探测炸）：回退 False，详情接口不炸"""

    def _boom():
        raise RuntimeError("registry unavailable")

    monkeypatch.setattr("strategy.routes.get_strategy_service", _boom)
    data = detail_client.get("/api/v1/workers/1/state").json()["data"]
    assert data["strategy_info"]["has_price_plan"] is False
