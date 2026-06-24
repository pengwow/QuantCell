import time
from axond.strategy_loop import StrategyLoop
from strategy.core.unified_strategy import UnifiedStrategy, StrategyContext
from strategy.core.bar import Bar
from strategy.core.order import Order


class RecordingStrategy(UnifiedStrategy):
    def __init__(self):
        self.bars = []

    def on_bar(self, bar: Bar, ctx: StrategyContext) -> list[Order]:
        self.bars.append(bar)
        return []


def test_strategy_loop_start_stop():
    strategy = RecordingStrategy()

    class MockAdapter:
        def connect(self): pass
        def disconnect(self): pass
        def get_ticker(self, symbol): return {"last": 50000.0, "open": 49000.0, "high": 51000.0, "low": 48000.0, "volume": 1000.0}

    loop = StrategyLoop(adapter=MockAdapter(), strategy=strategy, symbol="BTCUSDT", interval=0.1)
    loop.start()
    time.sleep(0.3)
    loop.stop()
    assert len(strategy.bars) >= 1
