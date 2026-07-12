# -*- coding: utf-8 -*-
"""BacktestLoop — 使用 axon_quant.backtest.BacktestEngine 的回测循环"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd

from axon_quant import (
    Action,
    BacktestEngine as _AxonBacktestEngine,
)

logger = logging.getLogger(__name__)

_DEFAULT_HALF_SPREAD_RATIO = 0.0005
_DEFAULT_DEPTH_LEVELS = 5
_DEFAULT_SIZE_PER_LEVEL = 100.0


@dataclass
class BacktestResult:
    """回测结果"""
    total_pnl: float = 0.0
    total_orders: int = 0
    fills: int = 0
    final_nav: float = 0.0
    max_drawdown: float = 0.0
    orders_accepted: int = 0
    orders_rejected: int = 0
    events_processed: int = 0
    duration_secs: float = 0.0
    total_fees: float = 0.0
    win_rate: float = 0.0
    sharpe_ratio: float = 0.0
    nav_peak: float = 0.0
    max_drawdown_pct: float = 0.0
    trade_records: list = field(default_factory=list)
    equity_curve: list = field(default_factory=list)
    data_start_ns: int = 0
    data_end_ns: int = 0
    bar_count: int = 0
    final_positions: dict = field(default_factory=dict)


class RuleStrategy(ABC):
    """规则策略基类 — 子类实现 on_bar() 返回 Action"""

    @abstractmethod
    def on_bar(self, bar: dict) -> Action:
        """处理一根K线，返回交易动作

        Args:
            bar: {"open", "high", "low", "close", "volume", "symbol", "timestamp_ns"}

        Returns:
            Action 对象
        """
        ...

    def on_start(self) -> None:
        """策略启动回调"""
        pass

    def on_stop(self) -> None:
        """策略停止回调"""
        pass


class BacktestLoop:
    """使用 axon_quant BacktestEngine 的回测循环

    Args:
        initial_cash: 初始资金
        force_liquidate: 回测结束时是否强制平仓
    """

    def __init__(
        self,
        initial_cash: float = 100_000.0,
        force_liquidate: bool = False,
    ):
        self._initial_cash = initial_cash
        self._default_force_liquidate = force_liquidate

    def run(
        self,
        strategy: RuleStrategy,
        data: pd.DataFrame,
        symbol: str = "BTCUSDT",
        force_liquidate: Optional[bool] = None,
    ) -> BacktestResult:
        """执行回测

        Args:
            strategy: 策略实例（实现 on_bar → Action）
            data: OHLCV DataFrame，索引为 DatetimeIndex
            symbol: 交易对符号
            force_liquidate: 是否强制平仓（None 用构造默认值）

        Returns:
            BacktestResult
        """
        effective_force_liquidate = (
            self._default_force_liquidate
            if force_liquidate is None
            else force_liquidate
        )

        engine = _AxonBacktestEngine(initial_cash=self._initial_cash)

        engine.with_seed_liquidity(
            half_spread=_DEFAULT_HALF_SPREAD_RATIO,
            depth_levels=_DEFAULT_DEPTH_LEVELS,
            size_per_level=_DEFAULT_SIZE_PER_LEVEL,
        )

        if effective_force_liquidate:
            engine.with_force_liquidate(True)

        strategy.on_start()
        total_orders = 0
        order_id = 0

        for idx, row in data.iterrows():
            ts = int(pd.Timestamp(idx).timestamp() * 1_000_000_000)
            close_price = float(row["Close"])

            engine.begin_bar(close_price, symbol)

            bar = {
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": close_price,
                "volume": float(row["Volume"]),
                "symbol": symbol,
                "timestamp_ns": ts,
            }

            action = strategy.on_bar(bar)
            total_orders += 1

            if str(action.action_type) in ("buy", "sell"):
                side = "Buy" if str(action.action_type) == "buy" else "Sell"
                quantity = abs(action.target_position) if action.target_position else 0.1

                order_id += 1
                from axon_quant.backtest import market_order as _market_order

                axon_order = _market_order(order_id, symbol, side, quantity)
                engine.push_event({
                    "type": "order_submitted",
                    "timestamp_ns": ts,
                    "order": axon_order,
                })

            # 逐 bar 撮合（不能用 run()，它会把所有订单延迟到最后）
            engine.step()

        strategy.on_stop()

        # 最终结算（处理剩余事件）
        result = engine.run()

        max_drawdown_usd = result.nav_peak * (result.max_drawdown_pct / 100.0)
        final_positions = dict(result.positions) if hasattr(result, "positions") else {}

        return BacktestResult(
            total_pnl=result.total_pnl,
            total_orders=total_orders,
            fills=result.fills,
            final_nav=result.final_nav,
            max_drawdown=max_drawdown_usd,
            orders_accepted=result.orders_accepted,
            orders_rejected=result.orders_rejected,
            events_processed=result.events_processed,
            duration_secs=result.duration_secs,
            total_fees=float(getattr(result, "total_fees", 0.0)),
            win_rate=float(getattr(result, "win_rate", 0.0)),
            sharpe_ratio=float(getattr(result, "sharpe_ratio", 0.0)),
            nav_peak=float(getattr(result, "nav_peak", 0.0)),
            max_drawdown_pct=float(getattr(result, "max_drawdown_pct", 0.0)),
            trade_records=list(getattr(result, "trades", [])),
            equity_curve=[list(p) for p in getattr(result, "equity_curve", [])],
            data_start_ns=int(pd.Timestamp(data.index[0]).timestamp() * 1e9) if len(data) > 0 else 0,
            data_end_ns=int(pd.Timestamp(data.index[-1]).timestamp() * 1e9) if len(data) > 0 else 0,
            bar_count=len(data),
            final_positions=final_positions,
        )
