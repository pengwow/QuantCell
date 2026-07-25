# -*- coding: utf-8 -*-
"""BacktestLoop — 使用 axon_quant.backtest.BacktestEngine 的回测循环"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd

from axon_bridge import (
    Action,
    BacktestEngine as _AxonBacktestEngine,
)
from axon_bridge.backtest import spot_instrument

logger = logging.getLogger(__name__)

_DEFAULT_HALF_SPREAD_RATIO = 0.0005
_DEFAULT_DEPTH_LEVELS = 5
_DEFAULT_SIZE_PER_LEVEL = 100.0
_DEFAULT_AUTO_REBALANCE_THRESHOLD = 0.001


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
        from strategy.base import BaseStrategy, StrategyContext

        effective_force_liquidate = (
            self._default_force_liquidate
            if force_liquidate is None
            else force_liquidate
        )

        # 解析 instrument: 从 symbol 如 BTCUSDT 提取 base/quote
        base, quote = self._parse_symbol(symbol)
        instrument = spot_instrument(base, quote)

        # axon_quant 0.10.0: 链式配置 API
        engine = (
            _AxonBacktestEngine(initial_cash=self._initial_cash)
            .with_seed(42)
            .with_seed_liquidity(
                half_spread=_DEFAULT_HALF_SPREAD_RATIO,
                depth_levels=_DEFAULT_DEPTH_LEVELS,
                size_per_level=_DEFAULT_SIZE_PER_LEVEL,
            )
            .with_auto_rebalance(threshold=_DEFAULT_AUTO_REBALANCE_THRESHOLD)
        )

        if effective_force_liquidate:
            engine = engine.with_force_liquidate(True)

        # 兼容 BaseStrategy 和 RuleStrategy 两种策略类型
        is_base_strategy = isinstance(strategy, BaseStrategy)
        ctx = None
        if is_base_strategy:
            ctx = StrategyContext(symbol=symbol, account_equity=self._initial_cash)
            strategy.on_start(ctx)
        else:
            strategy.on_start()

        total_orders = 0

        for idx, row in data.iterrows():
            # 优先使用 timestamp 列（纳秒时间戳），否则从 DatetimeIndex 转换
            if "timestamp" in row:
                ts = int(row["timestamp"])
            else:
                ts = int(pd.Timestamp(idx).timestamp() * 1_000_000_000)
            # 兼容大小写列名
            close_price = float(row.get("close", row.get("Close", 0.0)))

            # 0.10.0 API: begin_bar(price=, instrument=)
            engine.set_clock(ts)
            engine.begin_bar(price=close_price, instrument=instrument)

            bar = {
                "open": float(row.get("open", row.get("Open", close_price))),
                "high": float(row.get("high", row.get("High", close_price))),
                "low": float(row.get("low", row.get("Low", close_price))),
                "close": close_price,
                "volume": float(row.get("volume", row.get("Volume", 0.0))),
                "symbol": symbol,
                "timestamp_ns": ts,
            }

            # 更新 ctx 净值 (ponytail: 简化为固定 initial_cash)
            if is_base_strategy and ctx is not None:
                ctx.account_equity = self._initial_cash

            # 策略决策
            if is_base_strategy:
                action = strategy.on_bar(bar, ctx)
            else:
                action = strategy.on_bar(bar)
            total_orders += 1

            # 应用 Action: target_position 是 ratio (占 equity 比例)
            # 转换为绝对 qty = ratio * equity / price
            if str(action.action_type) in ("buy", "sell"):
                ratio = float(getattr(action, "target_position", 0.0) or 0.0)
                qty = (ratio * self._initial_cash / close_price) if close_price > 0 else 0.0
                engine.set_target_position(instrument, qty)

            # 触发调仓 + drain 事件
            engine.rebalance_to_target()
            while engine.pending_events > 0:
                engine.step()

        if is_base_strategy:
            strategy.on_stop(ctx)
        else:
            strategy.on_stop()

        # 最终结算
        result = engine.run()

        # axon 返回的 max_drawdown_pct 是小数形式（如 0.0023 表示 0.23%）
        # 转换为 USD 绝对值：max_drawdown_usd = nav_peak * drawdown_ratio
        raw_max_dd_pct = float(getattr(result, "max_drawdown_pct", 0.0))
        max_drawdown_usd = result.nav_peak * raw_max_dd_pct
        max_drawdown_pct_display = raw_max_dd_pct * 100.0  # 转换为百分比用于显示
        raw_win_rate = float(getattr(result, "win_rate", 0.0))
        win_rate_display = raw_win_rate * 100.0  # 转换为百分比用于显示
        final_positions = dict(result.positions) if hasattr(result, "positions") else {}

        # 构建 equity_curve: 使用 bar_nav_curve（每根K线一个点），格式适配前端
        equity_curve = []
        bar_nav = list(getattr(result, "bar_nav_curve", []))
        for ts_ns, nav in bar_nav:
            dt = datetime.fromtimestamp(ts_ns / 1e9, tz=timezone.utc)
            dt_str = dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
            nav_float = float(nav)
            equity_curve.append({
                # 大写字段（EquityChart 组件支持）
                "datetime": dt_str,
                "Equity": nav_float,
                # 小写兼容字段
                "equity": nav_float,
                "formatted_time": dt_str,
                "timestamp": int(ts_ns / 1e6),  # 毫秒级时间戳
            })

        # 构建 round-trip trades: 从 fills_detail 配对开平仓
        trade_records = self._build_round_trip_trades(
            list(getattr(result, "fills_detail", []))
        )

        # 获取数据时间范围：优先使用 timestamp 列
        if "timestamp" in data.columns and len(data) > 0:
            data_start_ns = int(data["timestamp"].iloc[0])
            data_end_ns = int(data["timestamp"].iloc[-1])
        elif len(data) > 0:
            data_start_ns = int(pd.Timestamp(data.index[0]).timestamp() * 1e9)
            data_end_ns = int(pd.Timestamp(data.index[-1]).timestamp() * 1e9)
        else:
            data_start_ns = 0
            data_end_ns = 0

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
            win_rate=win_rate_display,  # 百分比形式（如 71.43 表示 71.43%）
            sharpe_ratio=float(getattr(result, "sharpe_ratio", 0.0)),
            nav_peak=float(getattr(result, "nav_peak", 0.0)),
            max_drawdown_pct=max_drawdown_pct_display,  # 百分比形式（如 0.23 表示 0.23%）
            trade_records=trade_records,
            equity_curve=equity_curve,
            data_start_ns=data_start_ns,
            data_end_ns=data_end_ns,
            bar_count=len(data),
            final_positions=final_positions,
        )

    @staticmethod
    def _build_round_trip_trades(fills_detail: list[dict]) -> list[dict]:
        """从 fills_detail 配对构建 round-trip trades，兼容大写字段和前端格式。

        ponytail: 简单 FIFO 配对，只处理 Buy→Sell 多头平仓，不支持 short
        """
        if not fills_detail:
            return []

        trades: list[dict] = []
        open_positions: list[dict] = []  # FIFO queue of open buys

        for fill in fills_detail:
            side = fill.get("taker_side", "")
            qty = float(fill.get("quantity", 0.0))
            price = float(fill.get("price", 0.0))
            ts_ns = int(fill.get("timestamp_ns", 0))

            if side == "Buy":
                open_positions.append({
                    "entry_time_ns": ts_ns,
                    "entry_price": price,
                    "quantity": qty,
                    "remaining": qty,
                })
            elif side == "Sell" and open_positions:
                # FIFO 配对平仓
                remaining_to_close = qty
                while remaining_to_close > 1e-12 and open_positions:
                    open_pos = open_positions[0]
                    matched_qty = min(open_pos["remaining"], remaining_to_close)

                    entry_dt = datetime.fromtimestamp(open_pos["entry_time_ns"] / 1e9, tz=timezone.utc)
                    exit_dt = datetime.fromtimestamp(ts_ns / 1e9, tz=timezone.utc)
                    pnl = matched_qty * (price - open_pos["entry_price"])
                    entry_value = matched_qty * open_pos["entry_price"]
                    return_pct = (pnl / entry_value * 100.0) if entry_value > 0 else 0.0

                    # 同时提供大写字段（回测表格）和小写字段兼容（其他组件）
                    entry_time_str = entry_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
                    exit_time_str = exit_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
                    trades.append({
                        # 大写字段（前端 types/backtest.ts 中 Trade 接口）
                        "EntryTime": entry_time_str,
                        "ExitTime": exit_time_str,
                        "EntryPrice": open_pos["entry_price"],
                        "ExitPrice": price,
                        "Size": matched_qty,
                        "PnL": pnl,
                        "ReturnPct": return_pct,
                        "Direction": "long",
                        # 小写兼容字段（部分组件可能使用）
                        "entry_time": entry_time_str,
                        "exit_time": exit_time_str,
                        "entry_price": open_pos["entry_price"],
                        "exit_price": price,
                        "size": matched_qty,
                        "pnl": pnl,
                        "return_pct": return_pct,
                        "direction": "long",
                        "side": "sell",
                        "status": "FILLED",
                    })

                    open_pos["remaining"] -= matched_qty
                    remaining_to_close -= matched_qty
                    if open_pos["remaining"] < 1e-12:
                        open_positions.pop(0)

        return trades

    @staticmethod
    def _parse_symbol(symbol: str) -> tuple[str, str]:
        """解析 'BTCUSDT' / 'BTC-USDT' 为 (base, quote)。"""
        s = symbol.upper().replace("-", "").replace("_", "")
        for q in ("USDT", "USDC", "USD", "BTC", "ETH"):
            if s.endswith(q) and len(s) > len(q):
                return s[:-len(q)], q
        return "BTC", "USDT"
