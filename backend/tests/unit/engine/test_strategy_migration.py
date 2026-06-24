import pandas as pd
from strategies.unified_dual_ma import DualMAStrategy
from backtest.backtest_loop import BacktestLoop

def test_dual_ma_strategy_backtest():
    strategy = DualMAStrategy(fast_period=3, slow_period=5)
    loop = BacktestLoop(initial_cash=100_000.0)

    closes = [100 + i * 0.5 for i in range(20)]
    df = pd.DataFrame({
        "open": closes, "high": [c + 2 for c in closes],
        "low": [c - 2 for c in closes], "close": closes,
        "volume": [1000.0] * 20,
    }, index=pd.date_range("2024-01-01", periods=20, freq="h"))

    result = loop.run(strategy, df, symbol="BTCUSDT")
    assert result is not None
