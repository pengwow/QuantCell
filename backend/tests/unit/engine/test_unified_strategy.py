import pytest
from strategy.core.unified_strategy import UnifiedStrategy, StrategyContext
from strategy.core.bar import Bar
from strategy.core.order import Order, OrderSide

class MockStrategy(UnifiedStrategy):
    def __init__(self):
        self.bars_received = []

    def on_bar(self, bar: Bar, ctx: StrategyContext) -> list[Order]:
        self.bars_received.append(bar)
        if bar.close > 100:
            return [Order(symbol=bar.symbol, side=OrderSide.BUY, quantity=0.1)]
        return []

def test_strategy_receives_bars():
    strategy = MockStrategy()
    ctx = StrategyContext()
    bar = Bar(timestamp=1000, open=100, high=105, low=95, close=102, volume=1000, symbol="BTCUSDT")
    orders = strategy.on_bar(bar, ctx)
    assert len(strategy.bars_received) == 1
    assert len(orders) == 1
    assert orders[0].side == OrderSide.BUY

def test_strategy_context_get_position():
    ctx = StrategyContext()
    assert ctx.get_position("BTCUSDT") == 0.0
