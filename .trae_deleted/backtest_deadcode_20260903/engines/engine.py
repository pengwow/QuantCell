"""BacktestEngine 兼容层（已废弃）

ponytail: 原 BacktestEngine 已合并到 BacktestLoop，本文件仅作为向后兼容层。
         新代码应直接使用 backtest.backtest_loop.BacktestLoop。
"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pandas as pd

warnings.warn(
    "backtest.engines.BacktestEngine 已废弃，请直接使用 BacktestLoop",
    DeprecationWarning,
    stacklevel=2,
)


class BacktestEngine:
    """BacktestEngine 兼容层 — 内部委托给 BacktestLoop"""

    def __init__(self, config: dict[str, Any] | None = None):
        self._config = config or {}
        self._is_initialized = False

    def initialize(self) -> None:
        """初始化（兼容方法，无实际操作）"""
        if self._config.get("initial_capital", 100000.0) <= 0:
            msg = "initial_capital 必须 > 0"
            raise ValueError(msg)
        self._is_initialized = True

    def run_with_strategy(
        self,
        strategy: Any,
        data: pd.DataFrame,
        symbol: str = "BTCUSDT",
        force_liquidate: bool = False,
    ) -> dict[str, Any]:
        """执行回测 - 委托给 BacktestLoop"""
        if not self._is_initialized:
            msg = "引擎未初始化，请先调用 initialize()"
            raise RuntimeError(msg)

        if data is None or data.empty:
            msg = "data 不能为空"
            raise ValueError(msg)

        from backtest.backtest_loop import BacktestLoop

        initial_cash = self._config.get("initial_capital", 100000.0)
        loop = BacktestLoop(initial_cash=initial_cash)

        result = loop.run(
            strategy=strategy,
            data=data,
            symbol=symbol,
            force_liquidate=force_liquidate,
        )

        return {
            "initial_capital": initial_cash,
            "final_nav": result.final_nav,
            "total_pnl": result.total_pnl,
            "max_drawdown": result.max_drawdown,
            "max_drawdown_pct": result.max_drawdown_pct,
            "nav_peak": result.nav_peak,
            "orders_accepted": result.orders_accepted,
            "orders_rejected": result.orders_rejected,
            "fills": result.fills,
            "total_orders": result.total_orders,
            "events_processed": result.events_processed,
            "duration_secs": result.duration_secs,
            "win_rate": result.win_rate,
            "sharpe_ratio": result.sharpe_ratio,
            "total_fees": result.total_fees,
            "trade_count": len(result.trade_records),
            "trades": list(result.trade_records),
            "equity_curve": list(result.equity_curve),
            "data_start_ns": result.data_start_ns,
            "data_end_ns": result.data_end_ns,
            "bar_count": result.bar_count,
        }

    def cleanup(self) -> None:
        """释放资源（兼容方法，无实际操作）"""
        self._is_initialized = False


__all__ = ["BacktestEngine"]
