from dataclasses import dataclass

import pandas as pd

from strategy.core.bar import Bar
from strategy.core.unified_strategy import StrategyContext, UnifiedStrategy


@dataclass
class BacktestResult:
    total_pnl: float = 0.0
    total_orders: int = 0
    fills: int = 0
    final_nav: float = 0.0
    max_drawdown: float = 0.0


class BacktestLoop:
    def __init__(self, initial_cash: float = 100_000.0):
        self._initial_cash = initial_cash

    def run(
        self,
        strategy: UnifiedStrategy,
        data: pd.DataFrame,
        symbol: str = "BTCUSDT",
    ) -> BacktestResult:
        ctx = StrategyContext()
        strategy.on_start(ctx)

        total_orders = 0
        for idx, row in data.iterrows():
            ts = int(pd.Timestamp(idx).timestamp() * 1_000_000_000)
            bar = Bar(
                timestamp=ts,
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
                volume=row["volume"],
                symbol=symbol,
            )
            orders = strategy.on_bar(bar, ctx)
            total_orders += len(orders)

        strategy.on_stop(ctx)
        return BacktestResult(total_orders=total_orders, final_nav=self._initial_cash)
