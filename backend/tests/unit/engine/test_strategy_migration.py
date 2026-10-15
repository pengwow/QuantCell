"""旧 strategies/dual_ma 已迁移到 strategy/templates 的 BaseStrategy 版本。

冒烟断言：模板 DualMA 能在唯一 BacktestLoop 路径跑完整回测。
"""

from __future__ import annotations

import pandas as pd

from backtest.backtest_loop import BacktestLoop
from strategy.base import StrategyConfig
from strategy.templates.dual_ma import DualMA


def _make_ohlcv(n: int = 80) -> pd.DataFrame:
    idx = pd.date_range("2025-01-01", periods=n, freq="1h", tz="UTC")
    close = 100.0 + pd.Series(range(n), dtype="float64")
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": 1000.0,
        },
        index=idx,
    )


def test_template_dual_ma_runs_on_backtest_loop():
    strategy = DualMA(StrategyConfig(name="dual_ma", params={"fast": 5, "slow": 20}))
    result = BacktestLoop(initial_cash=100_000.0).run(strategy=strategy, data=_make_ohlcv(), symbol="BTCUSDT")
    assert result is not None
    assert result.final_nav > 0
