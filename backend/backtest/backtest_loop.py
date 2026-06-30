# -*- coding: utf-8 -*-
"""BacktestLoop — 使用 axon_quant.backtest.BacktestEngine 的回测循环

替代原简单 Python 循环，使用 axon_quant 的事件驱动回测引擎，
支持订单撮合、PnL 计算、最大回撤等完整回测功能。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd

from strategy.core.bar import Bar
from strategy.core.order import Order, OrderSide
from strategy.core.unified_strategy import StrategyContext, UnifiedStrategy

logger = logging.getLogger(__name__)

# axon_quant 导入（可选）
try:
    from axon_quant.backtest import (
        BacktestEngine as _AxonBacktestEngine,
        L1MatchingEngine as _L1MatchingEngine,
        limit_order as _limit_order,
    )
    AXON_AVAILABLE = True
except ImportError:
    AXON_AVAILABLE = False
    _AxonBacktestEngine = None
    _L1MatchingEngine = None
    _limit_order = None


@dataclass
class BacktestResult:
    """回测结果 — Stage 3 阶段 B 起扩展 RunResult 字段(从 axon_quant 直接读取)"""
    total_pnl: float = 0.0
    total_orders: int = 0
    fills: int = 0
    final_nav: float = 0.0
    max_drawdown: float = 0.0
    orders_accepted: int = 0
    orders_rejected: int = 0
    events_processed: int = 0
    duration_secs: float = 0.0
    # 阶段 B 新增(从 axon_quant RunResult 直接读取,不再应用层手算)
    total_fees: float = 0.0
    win_rate: float = 0.0
    sharpe_ratio: float = 0.0
    nav_peak: float = 0.0
    max_drawdown_pct: float = 0.0
    # trade_records 序列(每个 dict 一个平仓记录,字段同 axon_quant)
    trade_records: list = field(default_factory=list)
    # equity_curve 序列:list[(ts_ns, equity)]
    equity_curve: list = field(default_factory=list)
    # 数据时间范围(从 data.index 提取)
    data_start_ns: int = 0
    data_end_ns: int = 0
    bar_count: int = 0
    # 终态持仓(symbol → qty)
    final_positions: dict = field(default_factory=dict)


class AxonStrategyContext(StrategyContext):
    """扩展 StrategyContext，支持通过 axon_quant 引擎下单"""

    def __init__(self, engine: Any = None):
        super().__init__()
        self._engine = engine
        self._order_counter = 0
        self._pending_orders: list[dict] = []

    def buy(self, symbol: str, quantity: float, price: float = 0) -> str:
        """买入下单，返回 order_id"""
        self._order_counter += 1
        order_id = f"order_{self._order_counter}"

        if self._engine and AXON_AVAILABLE:
            order = _limit_order(
                self._order_counter,
                symbol,
                "Buy",
                price,
                quantity
            )
            self._pending_orders.append({
                "type": "order_submitted",
                "timestamp_ns": 0,  # 会在 run() 中设置
                "order": order
            })

        return order_id

    def sell(self, symbol: str, quantity: float, price: float = 0) -> str:
        """卖出下单，返回 order_id"""
        self._order_counter += 1
        order_id = f"order_{self._order_counter}"

        if self._engine and AXON_AVAILABLE:
            order = _limit_order(
                self._order_counter,
                symbol,
                "Sell",
                price,
                quantity
            )
            self._pending_orders.append({
                "type": "order_submitted",
                "timestamp_ns": 0,  # 会在 run() 中设置
                "order": order
            })

        return order_id

    def cancel(self, order_id: str) -> bool:
        """取消订单（暂不支持）"""
        logger.warning(f"cancel() 暂不支持: {order_id}")
        return False

    def get_pending_orders(self) -> list[dict]:
        """获取待处理订单"""
        return self._pending_orders.copy()

    def clear_pending_orders(self) -> None:
        """清空待处理订单"""
        self._pending_orders.clear()


class BacktestLoop:
    """使用 axon_quant.backtest.BacktestEngine 的回测循环

    当 axon_quant 不可用时，回退到简单 Python 循环（无订单执行）。

    Args:
        initial_cash: 初始资金（默认 100,000）
    """

    def __init__(self, initial_cash: float = 100_000.0):
        self._initial_cash = initial_cash

    def run(
        self,
        strategy: UnifiedStrategy,
        data: pd.DataFrame,
        symbol: str = "BTCUSDT",
    ) -> BacktestResult:
        """执行回测

        Args:
            strategy: 策略实例
            data: OHLCV DataFrame，索引为 DatetimeIndex
            symbol: 交易对符号

        Returns:
            BacktestResult 回测结果
        """
        if AXON_AVAILABLE:
            return self._run_with_axon(strategy, data, symbol)
        else:
            logger.warning("axon_quant 不可用，使用简单 Python 循环（无订单执行）")
            return self._run_simple(strategy, data, symbol)

    def _run_with_axon(
        self,
        strategy: UnifiedStrategy,
        data: pd.DataFrame,
        symbol: str,
    ) -> BacktestResult:
        """使用 axon_quant.backtest.BacktestEngine 执行回测

        工作原理:
        1. 创建 BacktestEngine + L1MatchingEngine
        2. 遍历 DataFrame，将每行转换为 Bar 对象
        3. 策略处理 Bar，返回订单列表
        4. 将订单推入 BacktestEngine
        5. 引擎执行订单撮合和 PnL 计算
        """
        # 创建 axon 引擎（使用 L1 撮合引擎）
        engine = _AxonBacktestEngine(initial_cash=self._initial_cash)
        matcher = _L1MatchingEngine()
        engine.with_matching_engine(matcher)

        # 创建 StrategyContext
        ctx = StrategyContext()
        strategy.on_start(ctx)

        total_orders = 0
        order_id_counter = 0

        # 遍历数据，执行策略并提交订单
        for idx, row in data.iterrows():
            ts = int(pd.Timestamp(idx).timestamp() * 1_000_000_000)

            # 创建 Bar 对象
            # 注意:backtest_data_provider._normalize_dataframe 默认把列名转大写
            # (Open/High/Low/Close/Volume),backtest_loop 必须用大写列名与
            # 实际数据流对齐(否则 CLI 报 KeyError 'open')
            bar = Bar(
                timestamp=ts,
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                volume=float(row["Volume"]),
                symbol=symbol,
            )

            # 策略处理 Bar，生成订单
            orders = strategy.on_bar(bar, ctx)
            total_orders += len(orders)

            # 提交订单到 axon 引擎
            for order in orders:
                order_id_counter += 1
                side = "Buy" if order.side == OrderSide.BUY else "Sell"
                price = order.price if order.price > 0 else float(row["Close"])

                axon_order = _limit_order(
                    order_id_counter,
                    order.symbol or symbol,
                    side,
                    price,
                    order.quantity
                )

                engine.push_event({
                    "type": "order_submitted",
                    "timestamp_ns": ts,
                    "order": axon_order
                })

        # 策略停止
        strategy.on_stop(ctx)

        # 执行回测
        result = engine.run()

        # 转换结果
        # Stage 3 阶段 B:从 axon_quant.RunResult 直接读新字段,
        # 不再应用层手算手续费/夏普/胜率/最大回撤百分比
        # max_drawdown(USD 绝对值) = nav_peak * (max_drawdown_pct / 100)
        max_drawdown_usd = result.nav_peak * (result.max_drawdown_pct / 100.0)
        # 终态持仓 dict(symbol -> qty),axon 已暴露为 dict
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
            # 阶段 B 字段(从 RunResult 直接读取)
            total_fees=float(getattr(result, "total_fees", 0.0)),
            win_rate=float(getattr(result, "win_rate", 0.0)),
            sharpe_ratio=float(getattr(result, "sharpe_ratio", 0.0)),
            nav_peak=float(getattr(result, "nav_peak", 0.0)),
            max_drawdown_pct=float(getattr(result, "max_drawdown_pct", 0.0)),
            trade_records=list(getattr(result, "trades", [])),
            equity_curve=[list(p) for p in getattr(result, "equity_curve", [])],
            data_start_ns=int(data.index[0].timestamp() * 1e9) if len(data) > 0 else 0,
            data_end_ns=int(data.index[-1].timestamp() * 1e9) if len(data) > 0 else 0,
            bar_count=len(data),
            final_positions=final_positions,
        )

    def _run_simple(
        self,
        strategy: UnifiedStrategy,
        data: pd.DataFrame,
        symbol: str,
    ) -> BacktestResult:
        """简单 Python 循环（无 axon_quant，无订单执行）"""
        ctx = StrategyContext()
        strategy.on_start(ctx)

        total_orders = 0
        for idx, row in data.iterrows():
            ts = int(pd.Timestamp(idx).timestamp() * 1_000_000_000)
            bar = Bar(
                timestamp=ts,
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                volume=float(row["Volume"]),
                symbol=symbol,
            )
            orders = strategy.on_bar(bar, ctx)
            total_orders += len(orders)

        strategy.on_stop(ctx)
        return BacktestResult(
            total_orders=total_orders,
            final_nav=self._initial_cash
        )
