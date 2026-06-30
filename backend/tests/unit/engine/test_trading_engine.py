from engine.trading_engine import TradingEngine
from engine.config import EngineConfig
from strategy.core.unified_strategy import UnifiedStrategy, StrategyContext
from strategy.core.bar import Bar
from strategy.core.order import Order, OrderSide


class SimpleStrategy(UnifiedStrategy):
    def on_bar(self, bar: Bar, ctx: StrategyContext) -> list[Order]:
        return []


def test_trading_engine_creation():
    config = EngineConfig(exchange="binance", trading_mode="paper")
    engine = TradingEngine(config)
    assert engine is not None


def test_trading_engine_registers_strategy():
    config = EngineConfig(exchange="binance", trading_mode="paper")
    engine = TradingEngine(config)
    strategy = SimpleStrategy()
    sid = engine.register_strategy(strategy, symbols=["BTCUSDT"])
    assert sid is not None
    assert len(engine.list_strategies()) == 1


def test_trading_engine_runs_backtest():
    import pandas as pd
    from engine.trading_engine import TradingEngine
    from engine.config import EngineConfig
    from strategy.core.unified_strategy import UnifiedStrategy, StrategyContext
    from strategy.core.bar import Bar
    from strategy.core.order import Order, OrderSide

    class BuyOnceStrategy(UnifiedStrategy):
        def __init__(self):
            self.done = False
        def on_bar(self, bar: Bar, ctx: StrategyContext) -> list[Order]:
            if not self.done:
                self.done = True
                return [Order(symbol=bar.symbol, side=OrderSide.BUY, quantity=0.1)]
            return []

    config = EngineConfig(exchange="binance", trading_mode="paper")
    engine = TradingEngine(config)
    strategy = BuyOnceStrategy()

    df = pd.DataFrame({
        # backtest_loop 期望小写列名
        "open": [100.0, 101.0], "high": [105.0, 106.0],
        "low": [95.0, 96.0], "close": [102.0, 103.0],
        "volume": [1000.0, 1100.0],
    }, index=pd.date_range("2024-01-01", periods=2, freq="h"))

    result = engine.run_backtest(strategy, df, symbol="BTCUSDT")
    assert result.total_orders >= 1
