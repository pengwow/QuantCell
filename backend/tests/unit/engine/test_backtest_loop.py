import pandas as pd
from backtest.backtest_loop import BacktestLoop, BacktestResult
from strategy.core.unified_strategy import UnifiedStrategy, StrategyContext
from strategy.core.bar import Bar
from strategy.core.order import Order, OrderSide


class BuyAndHoldStrategy(UnifiedStrategy):
    def __init__(self):
        self.bought = False

    def on_bar(self, bar: Bar, ctx: StrategyContext) -> list[Order]:
        if not self.bought:
            self.bought = True
            return [Order(symbol=bar.symbol, side=OrderSide.BUY, quantity=0.1, price=bar.close)]
        return []


def test_backtest_loop_runs():
    strategy = BuyAndHoldStrategy()
    loop = BacktestLoop(initial_cash=100_000.0)

    df = pd.DataFrame({
        "open": [100.0, 101.0, 102.0],
        "high": [105.0, 106.0, 107.0],
        "low": [95.0, 96.0, 97.0],
        "close": [102.0, 103.0, 104.0],
        "volume": [1000.0, 1100.0, 1200.0],
    }, index=pd.date_range("2024-01-01", periods=3, freq="h"))

    result = loop.run(strategy, df, symbol="BTCUSDT")
    assert isinstance(result, BacktestResult)
    assert result.total_orders >= 1
