import pandas as pd
from strategies.dual_ma import DualMA
from backtest.backtest_loop import BacktestLoop

def test_dual_ma_strategy_backtest():
    strategy = DualMA(fast=3, slow=5)
    loop = BacktestLoop(initial_cash=100_000.0)

    closes = [100 + i * 0.5 for i in range(20)]
    # 真实 Binance schema(大写列名)以匹配 backtest_loop 内部实现
    df = pd.DataFrame({
        "Open": closes, "High": [c + 2 for c in closes],
        "Low": [c - 2 for c in closes], "Close": closes,
        "Volume": [1000.0] * 20,
    }, index=pd.date_range("2024-01-01", periods=20, freq="h"))

    result = loop.run(strategy, df, symbol="BTCUSDT")
    assert result is not None
