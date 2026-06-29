# -*- coding: utf-8 -*-
"""axon 量化策略基类 — 不依赖任何外部量化框架"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from axond.types import Bar, InstrumentId, OrderType, Position, PositionSide
from utils.logger import get_logger, LogType


# 获取模块日志器
_logger = get_logger("axond.strategy", LogType.APPLICATION)


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

    def on_start(self, context: Any = None) -> None:
        """策略启动回调。

        Args:
            context: 兼容 ``StrategyLoop`` 传入的 ``StrategyContext``，
                旧版 ``AxonStrategy`` 子类可不使用该参数。
        """
        self.start_time = datetime.now()

    def on_stop(self, context: Any = None) -> None:
        """策略停止回调。

        Args:
            context: 兼容 ``StrategyLoop`` 传入的 ``StrategyContext``。
        """
        self.end_time = datetime.now()

    def on_bar(self, bar: Bar, context: Any = None) -> None:
        """收到 K 线数据回调。子类应重写此方法。

        Args:
            bar: K 线数据。
            context: 兼容 ``StrategyLoop`` 传入的 ``StrategyContext``。
        """
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

    # ============ 持仓状态便捷方法 ============

    def is_flat(self, symbol: str) -> bool:
        """判断指定品种是否无持仓"""
        return self.get_position_size(symbol) == 0.0

    def is_net_long(self, symbol: str) -> bool:
        """判断指定品种是否净多头持仓"""
        return self.get_position_size(symbol) > 0.0

    def is_net_short(self, symbol: str) -> bool:
        """判断指定品种是否净空头持仓"""
        return self.get_position_size(symbol) < 0.0

    def close_all_positions(self) -> List[dict]:
        """关闭所有品种的持仓，返回操作结果列表"""
        results = []
        for symbol in list(self._positions.keys()):
            results.append(self.close_position(symbol))
        return results

    def cancel_all_orders(self) -> int:
        """取消所有未成交订单（占位实现）。

        Returns:
            取消的订单数量。真实实盘场景需要对接 exchange adapter。
        """
        if not self._engine:
            return 0
        # 占位：真实场景应调用 exchange 的取消订单接口
        return 0

    # ============ 日志便捷方法 ============

    def log_info(self, msg: str) -> None:
        """记录信息日志"""
        _logger.info(f"[{self.__class__.__name__}] {msg}")

    def log_warning(self, msg: str) -> None:
        """记录警告日志"""
        _logger.warning(f"[{self.__class__.__name__}] {msg}")

    def log_error(self, msg: str) -> None:
        """记录错误日志"""
        _logger.error(f"[{self.__class__.__name__}] {msg}")

    def log_debug(self, msg: str) -> None:
        """记录调试日志"""
        _logger.debug(f"[{self.__class__.__name__}] {msg}")
