# -*- coding: utf-8 -*-
"""axon 量化策略基类 — 不依赖任何外部量化框架"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from axond.types import Bar, InstrumentId, OrderType, Position, PositionSide


class AxonStrategy:
    """axon 量化策略基类。

    提供 on_start/on_bar/on_stop 生命周期和 buy/sell/close_position 下单接口。
    子类应重写 on_bar() 实现具体交易逻辑。

    Attributes:
        config: 策略配置。
        bars_processed: 已处理 K 线数量。
        start_time: 策略启动时间。
        end_time: 策略停止时间。
    """

    def __init__(self, config: Any):
        self.config = config
        self.bars_processed: int = 0
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self._positions: Dict[str, Position] = {}
        self._orders: List[dict] = []
        self._engine: Any = None

    def on_start(self) -> None:
        """策略启动回调"""
        self.start_time = datetime.now()

    def on_stop(self) -> None:
        """策略停止回调"""
        self.end_time = datetime.now()

    def on_bar(self, bar: Bar) -> None:
        """收到 K 线数据回调。子类应重写此方法。"""
        self.bars_processed += 1

    def buy(
        self,
        symbol: str,
        quantity: float,
        price: Optional[float] = None,
        order_type: OrderType = OrderType.LIMIT,
    ) -> dict:
        """买入下单。

        Args:
            symbol: 交易对符号。
            quantity: 交易数量。
            price: 限价价格（市价单可为 None）。
            order_type: 订单类型。

        Returns:
            订单字典。
        """
        order = {
            "id": len(self._orders) + 1,
            "symbol": symbol,
            "side": "Buy",
            "type": order_type.value.lower(),
            "quantity": quantity,
            "tif": "GTC",
        }
        if price is not None:
            order["price"] = price
        self._orders.append(order)
        if self._engine:
            self._engine.submit_order(order, int(datetime.now().timestamp() * 1_000_000_000))
        return order

    def sell(
        self,
        symbol: str,
        quantity: float,
        price: Optional[float] = None,
        order_type: OrderType = OrderType.LIMIT,
    ) -> dict:
        """卖出下单。

        Args:
            symbol: 交易对符号。
            quantity: 交易数量。
            price: 限价价格（市价单可为 None）。
            order_type: 订单类型。

        Returns:
            订单字典。
        """
        order = {
            "id": len(self._orders) + 1,
            "symbol": symbol,
            "side": "Sell",
            "type": order_type.value.lower(),
            "quantity": quantity,
            "tif": "GTC",
        }
        if price is not None:
            order["price"] = price
        self._orders.append(order)
        if self._engine:
            self._engine.submit_order(order, int(datetime.now().timestamp() * 1_000_000_000))
        return order

    def get_position(self, symbol: str) -> Optional[Position]:
        """获取持仓。"""
        return self._positions.get(symbol)

    def get_position_size(self, symbol: str) -> float:
        """获取持仓数量。无持仓返回 0。"""
        pos = self.get_position(symbol)
        if pos is None:
            return 0.0
        return float(pos.quantity) if pos.side == PositionSide.LONG else -float(pos.quantity)

    def close_position(self, symbol: str) -> dict:
        """平仓（发送反向订单）。"""
        pos = self.get_position(symbol)
        if pos is None:
            return {"error": "no position"}
        qty = float(pos.quantity)
        if pos.side == PositionSide.LONG:
            return self.sell(symbol, qty)
        else:
            return self.buy(symbol, qty)
