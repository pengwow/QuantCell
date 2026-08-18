"""StrategyLoop 风控和 qty 转换测试"""

from __future__ import annotations

from dataclasses import dataclass

from strategy.loop import StrategyLoop


@dataclass
class FakeAction:
    action_type: str
    confidence: float
    target_position: float


class FakeStrategy:
    """测试用策略：返回固定 Action"""

    def __init__(self, action):
        self._action = action
        self.started = False
        self.stopped = False
        self.fills = []

    def on_start(self, ctx=None):
        self.started = True

    def on_stop(self, ctx=None):
        self.stopped = True

    def on_bar(self, bar, ctx=None):
        return self._action

    def on_fill(self, fill, ctx=None):
        self.fills.append(fill)


class FakeAdapter:
    """测试用交易所适配器"""

    def __init__(self):
        self.connected = False
        self.subscribed = []
        self.orders = []
        self.disconnected = False
        self._ticker = {
            "open": 65000,
            "high": 65100,
            "low": 64900,
            "last": 65050,
            "volume": 100.0,
        }

    def connect(self):
        self.connected = True

    def disconnect(self):
        self.disconnected = True

    def subscribe(self, symbols):
        self.subscribed = list(symbols)

    def get_ticker(self, symbol):
        return self._ticker

    def place_order(self, order_dict):
        self.orders.append(order_dict)
        return {"order_id": "test_123", "status": "accepted"}


class FakeRiskEngine:
    """测试用风控引擎：通过 check_passed 控制结果"""

    def __init__(self, check_passed: bool = True, reason: str | None = None):
        self.check_passed = check_passed
        self.reason = reason
        self.checked_orders = []

    def check_order(self, order, portfolio):
        self.checked_orders.append(order)
        return {"passed": self.check_passed, "reason": self.reason}


def test_qty_conversion_target_position_is_ratio():
    """target_position=0.1 应转换为 qty=0.1*100000/65050 ≈ 0.1537"""
    adapter = FakeAdapter()
    strategy = FakeStrategy(FakeAction("buy", confidence=0.8, target_position=0.1))
    loop = StrategyLoop(
        adapter=adapter,
        strategy=strategy,
        symbol="BTCUSDT",
        interval=100.0,  # 大间隔，手动控制
        risk_engine=FakeRiskEngine(check_passed=True),
        account_equity=100_000.0,
    )

    strategy.on_start()
    action = strategy.on_bar({})
    # 直接调用 _execute_action 测试 qty 转换
    loop._execute_action(action, 65050.0)

    assert len(adapter.orders) == 1
    order = adapter.orders[0]
    # qty = ratio * equity / price = 0.1 * 100000 / 65050 ≈ 0.1537
    assert abs(order["quantity"] - (0.1 * 100_000 / 65050)) < 1e-6
    assert order["side"] == "Buy"
    assert order["symbol"] == "BTCUSDT"


def test_risk_engine_rejects_order():
    """风控拒绝时不下单"""
    adapter = FakeAdapter()
    strategy = FakeStrategy(FakeAction("buy", confidence=0.8, target_position=0.5))
    risk = FakeRiskEngine(check_passed=False, reason="position_limit_exceeded")
    rejected_events = []
    loop = StrategyLoop(
        adapter=adapter,
        strategy=strategy,
        symbol="BTCUSDT",
        interval=100.0,
        risk_engine=risk,
        account_equity=100_000.0,
        event_callback=lambda evt_type, data: (
            rejected_events.append((evt_type, data)) if evt_type == "order.rejected" else None
        ),
    )

    action = strategy.on_bar({})
    loop._execute_action(action, 65000.0)

    assert len(adapter.orders) == 0, "风控拒绝的订单不应被下到交易所"
    assert len(risk.checked_orders) == 1
    assert len(rejected_events) == 1
    assert rejected_events[0][1]["reason"] == "position_limit_exceeded"


def test_low_confidence_filtered():
    """置信度 < 0.3 的信号不下单"""
    adapter = FakeAdapter()
    strategy = FakeStrategy(FakeAction("buy", confidence=0.2, target_position=0.1))
    risk = FakeRiskEngine(check_passed=True)
    loop = StrategyLoop(
        adapter=adapter,
        strategy=strategy,
        symbol="BTCUSDT",
        interval=100.0,
        risk_engine=risk,
        account_equity=100_000.0,
    )

    action = strategy.on_bar({})
    loop._execute_action(action, 65000.0)

    assert len(adapter.orders) == 0, "低置信度信号应被过滤"
    assert len(risk.checked_orders) == 0, "低置信度信号不应进入风控检查"


def test_no_risk_engine_still_places_order():
    """未注入风控引擎时直接下单（兼容模式）"""
    adapter = FakeAdapter()
    strategy = FakeStrategy(FakeAction("sell", confidence=0.9, target_position=0.05))
    loop = StrategyLoop(
        adapter=adapter,
        strategy=strategy,
        symbol="BTCUSDT",
        interval=100.0,
        risk_engine=None,
        account_equity=100_000.0,
    )

    action = strategy.on_bar({})
    loop._execute_action(action, 65000.0)

    assert len(adapter.orders) == 1
    assert adapter.orders[0]["side"] == "Sell"


def test_event_callback_on_order_placed():
    """订单成功后触发 order.placed 回调"""
    adapter = FakeAdapter()
    strategy = FakeStrategy(FakeAction("buy", confidence=0.8, target_position=0.1))
    events = []
    loop = StrategyLoop(
        adapter=adapter,
        strategy=strategy,
        symbol="BTCUSDT",
        interval=100.0,
        risk_engine=FakeRiskEngine(check_passed=True),
        account_equity=100_000.0,
        event_callback=lambda evt_type, data: events.append((evt_type, data)),
    )

    action = strategy.on_bar({})
    loop._execute_action(action, 65050.0)

    placed = [e for e in events if e[0] == "order.placed"]
    assert len(placed) == 1
    assert placed[0][1]["side"] == "Buy"
    assert placed[0][1]["quantity"] > 0
