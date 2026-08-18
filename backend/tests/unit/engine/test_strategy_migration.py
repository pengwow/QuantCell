import pandas as pd

from backtest.backtest_loop import BacktestLoop
from strategies.dual_ma import DualMA, DualMAConfig


def test_dual_ma_strategy_backtest():
    config = DualMAConfig(
        instrument_ids=["BTCUSDT"],
        bar_types=["BTCUSDT-1h"],
        fast_period=3,
        slow_period=5,
    )
    strategy = DualMA(config=config)
    loop = BacktestLoop(initial_cash=100_000.0)

    closes = [100 + i * 0.5 for i in range(20)]
    df = pd.DataFrame(
        {
            "Open": closes,
            "High": [c + 2 for c in closes],
            "Low": [c - 2 for c in closes],
            "Close": closes,
            "Volume": [1000.0] * 20,
        },
        index=pd.date_range("2024-01-01", periods=20, freq="h"),
    )

    result = loop.run(strategy, df, symbol="BTCUSDT")
    assert result is not None
