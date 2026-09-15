"""P0-3 风控↔引擎集成契约测试(真实 RiskService + StrategyLoop)。

覆盖报告 4.3「风控与引擎集成 P0 缺口」的端到端链路:
策略信号 → 真实风控引擎(非 Fake)评估 → Reject 阻断下单 / Allow 放行。
同时钉住 RiskService.check_order 返回 {"passed": bool} 的 loop 依赖契约。
"""

from __future__ import annotations

from dataclasses import dataclass

from services.risk_service import RiskService
from strategy.loop import StrategyLoop


@dataclass
class FakeAction:
    action_type: str
    confidence: float
    target_position: float


class FakeStrategy:
    """测试用策略:返回固定 Action。"""

    def __init__(self, action):
        self._action = action

    def on_start(self, ctx=None):
        pass

    def on_stop(self, ctx=None):
        pass

    def on_bar(self, bar, ctx=None):
        return self._action

    def on_fill(self, fill, ctx=None):
        pass


class FakeAdapter:
    """测试用交易所适配器:记录 place_order 调用。"""

    def __init__(self):
        self.orders: list[dict] = []
        self._ticker = {
            "open": 65000,
            "high": 65100,
            "low": 64900,
            "last": 65050,
            "volume": 100.0,
        }

    def connect(self):
        pass

    def disconnect(self):
        pass

    def subscribe(self, symbols):
        pass

    def get_ticker(self, symbol):
        return self._ticker

    def place_order(self, order_dict):
        self.orders.append(order_dict)
        return {"order_id": "test_123", "status": "accepted"}


def _make_loop(risk_engine, target_position: float, actions: list[tuple], adapter) -> StrategyLoop:
    """构造注入指定风控引擎的 StrategyLoop,事件写入 actions 列表。"""
    strategy = FakeStrategy(FakeAction("buy", confidence=0.9, target_position=target_position))
    return StrategyLoop(
        adapter=adapter,
        strategy=strategy,
        symbol="BTCUSDT",
        interval=100.0,
        risk_engine=risk_engine,
        account_equity=100_000.0,
        event_callback=lambda evt_type, data: actions.append((evt_type, data)),
    )


def test_risk_service_contract_shape() -> None:
    """RiskService.check_order 返回 {"passed": bool, "reason"},loop 依赖该契约。"""
    svc = RiskService({"max_order_value": 500.0})
    outcome = svc.check_order(
        {"symbol": "BTCUSDT", "side": "Buy", "quantity": 100.0, "price": 100.0},
        {"cash": {"USD": 100_000.0}},
    )
    assert set(outcome) == {"passed", "reason"}
    assert outcome["passed"] is False
    assert outcome["reason"]  # 拒绝时 reason 非空


def test_real_risk_rejects_oversized_order() -> None:
    """真实风控拒绝超限订单 → 订单不下到交易所、发 order.rejected 事件。"""
    events: list[tuple[str, dict]] = []
    adapter = FakeAdapter()
    svc = RiskService({"max_order_value": 500.0})
    loop = _make_loop(svc, target_position=0.5, actions=events, adapter=adapter)

    action = loop._strategy.on_bar({})
    loop._execute_action(action, 65_000.0)

    assert adapter.orders == []  # 风控拒绝的订单不能到达交易所
    rejected = [e for e in events if e[0] == "order.rejected"]
    assert len(rejected) == 1
    assert rejected[0][1]["reason"]


def test_real_risk_allows_small_order() -> None:
    """同一引擎在订单量受控时放行 → 正常下单并触发 order.placed。"""
    events: list[tuple[str, dict]] = []
    adapter = FakeAdapter()
    svc = RiskService({"max_order_value": 5_000.0})
    loop = _make_loop(svc, target_position=0.005, actions=events, adapter=adapter)

    action = loop._strategy.on_bar({})
    loop._execute_action(action, 65_000.0)

    assert len(adapter.orders) == 1
    placed = [e for e in events if e[0] == "order.placed"]
    assert len(placed) == 1


def test_loop_rejected_count_tracked() -> None:
    """风控拒绝累计 rejected_count(健康度指标),且循环流程不中断。"""
    adapter = FakeAdapter()
    svc = RiskService({"max_order_value": 500.0})
    loop = _make_loop(svc, target_position=0.5, actions=[], adapter=adapter)

    loop._execute_action(loop._strategy.on_bar({}), 65_000.0)
    assert loop._rejected_count == 1
    loop._execute_action(loop._strategy.on_bar({}), 65_000.0)
    assert loop._rejected_count == 2
    assert adapter.orders == []


def test_no_risk_engine_places_order() -> None:
    """未注入风控引擎时保持兼容:直接下单(既有语义回归)。"""
    adapter = FakeAdapter()
    loop = _make_loop(None, target_position=0.05, actions=[], adapter=adapter)

    loop._execute_action(loop._strategy.on_bar({}), 65_000.0)
    assert len(adapter.orders) == 1
