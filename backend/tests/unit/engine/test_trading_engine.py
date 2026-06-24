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
