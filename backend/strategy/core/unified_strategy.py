# -*- coding: utf-8 -*-
"""UnifiedStrategy — 统一策略基类

提供 on_start/on_bar/on_stop 生命周期和 buy/sell/cancel 交易接口。
子类应重写 on_bar() 实现具体交易逻辑。

设计文档: docs/compose/specs/2026-06-24-core-trading-engine-design.md
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

from .bar import Bar
from .order import Order, OrderSide

logger = logging.getLogger(__name__)


class StrategyContext:
    """策略上下文 — 注入交易接口

    提供 buy/sell/cancel 交易接口和 get_position 持仓查询。
    子类 AxonStrategyContext 可注入 axon_quant 引擎实现真实下单。

    Attributes:
        _positions: 持仓字典 {symbol: quantity}
        _engine: 底层引擎（axon_quant BacktestEngine 或 ExchangeAdapter）
        _order_counter: 订单计数器
        _pending_orders: 待处理订单列表
    """

    def __init__(self, engine: Any = None):
        self._positions: dict[str, float] = {}
        self._engine = engine
        self._order_counter = 0
        self._pending_orders: list[dict] = []

    def buy(self, symbol: str, quantity: float, price: float = 0) -> str:
        """买入下单

        Args:
            symbol: 交易对符号
            quantity: 买入数量
            price: 限价价格（市价单为 0）

        Returns:
            order_id: 订单 ID
        """
        self._order_counter += 1
        order_id = f"order_{self._order_counter}"

        # 更新本地持仓
        current = self._positions.get(symbol, 0.0)
        self._positions[symbol] = current + quantity

        logger.debug(f"Buy order: {order_id} {symbol} {quantity}@{price}")
        return order_id

    def sell(self, symbol: str, quantity: float, price: float = 0) -> str:
        """卖出下单

        Args:
            symbol: 交易对符号
            quantity: 卖出数量
            price: 限价价格（市价单为 0）

        Returns:
            order_id: 订单 ID
        """
        self._order_counter += 1
        order_id = f"order_{self._order_counter}"

        # 更新本地持仓
        current = self._positions.get(symbol, 0.0)
        self._positions[symbol] = current - quantity

        logger.debug(f"Sell order: {order_id} {symbol} {quantity}@{price}")
        return order_id

    def cancel(self, order_id: str) -> bool:
        """取消订单

        Args:
            order_id: 订单 ID

        Returns:
            是否取消成功
        """
        logger.warning(f"cancel() 暂不支持: {order_id}")
        return False

    def get_position(self, symbol: str) -> float:
        """获取持仓数量

        Args:
            symbol: 交易对符号

        Returns:
            持仓数量（正数为多头，负数为空头）
        """
        return self._positions.get(symbol, 0.0)

    def get_pending_orders(self) -> list[dict]:
        """获取待处理订单"""
        return self._pending_orders.copy()

    def clear_pending_orders(self) -> None:
        """清空待处理订单"""
        self._pending_orders.clear()


class UnifiedStrategy(ABC):
    """统一策略基类 — axon 风格 (float/str)

    子类应重写 on_bar() 实现具体交易逻辑。
    可选重写 on_start() 和 on_stop() 进行初始化和清理。

    示例:
        class MyStrategy(UnifiedStrategy):
            def on_bar(self, bar: Bar, ctx: StrategyContext) -> list[Order]:
                if bar.close > 100:
                    return [Order(symbol=bar.symbol, side=OrderSide.BUY, quantity=0.1)]
                return []
    """

    def on_start(self, ctx: StrategyContext) -> None:
        """策略启动回调

        Args:
            ctx: 策略上下文
        """
        pass

    @abstractmethod
    def on_bar(self, bar: Bar, ctx: StrategyContext) -> list[Order]:
        """收到 K 线数据回调

        Args:
            bar: K 线数据
            ctx: 策略上下文

        Returns:
            订单列表
        """
        ...

    def on_stop(self, ctx: StrategyContext) -> None:
        """策略停止回调

        Args:
            ctx: 策略上下文
        """
        pass
