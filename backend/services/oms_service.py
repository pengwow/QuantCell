"""OMS Service — axon_quant.oms 订单管理服务

包装 axon_quant.oms.OrderManager，提供订单提交、取消、查询、持仓快照等功能。
当 axon_quant 不可用时提供清晰的错误信息。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# axon_quant 导入(走适配层,业务代码不直接 import 第三方包)
try:
    from axon_bridge import (
        Order as _Order,
    )
    from axon_bridge import (
        OrderManager as _OrderManager,
    )
    from axon_bridge import (
        OrderStatus as _OrderStatus,
    )
    from axon_bridge import (
        OrderType as _OrderType,
    )
    from axon_bridge import (
        Portfolio as _Portfolio,
    )
    from axon_bridge import (
        Position as _Position,
    )
    from axon_bridge import (
        Side as _Side,
    )

    AXON_AVAILABLE = True
except ImportError:
    AXON_AVAILABLE = False
    _OrderManager = None
    _Order = None
    _Portfolio = None
    _Position = None
    _Side = None
    _OrderType = None
    _OrderStatus = None


class OMSService:
    """订单管理服务

    包装 axon_quant.oms.OrderManager，提供订单管理功能。

    Example:
        >>> oms = OMSService()
        >>> order_id = oms.submit_order({
        ...     "symbol": "BTCUSDT",
        ...     "side": "Buy",
        ...     "type": "limit",
        ...     "quantity": 0.1,
        ...     "price": 50000.0
        ... })
        >>> oms.cancel_order(order_id)
        >>> snapshot = oms.snapshot()
    """

    def __init__(self):
        """初始化 OMS 服务"""
        if not AXON_AVAILABLE:
            msg = "axon_quant.oms 不可用，请安装 axon_quant: pip install axon_quant"
            raise RuntimeError(msg)
        self._manager = _OrderManager()
        logger.info("OMS 服务已初始化")

    def submit_order(self, order_dict: dict[str, Any]) -> str:
        """提交订单

        Args:
            order_dict: 订单字典，包含:
                - symbol: 交易对符号
                - side: "Buy" 或 "Sell"
                - type: "limit" 或 "market"
                - quantity: 数量
                - price: 价格（限价单必填）
                - tif: 有效期（默认 "GTC"）

        Returns:
            order_id: 订单 ID
        """
        # 创建 Order 对象
        side = _Side.BUY if order_dict.get("side", "Buy") == "Buy" else _Side.SELL
        order_type = _OrderType.LIMIT if order_dict.get("type", "limit") == "limit" else _OrderType.MARKET

        order = _Order(
            symbol=order_dict.get("symbol", ""),
            side=side,
            order_type=order_type,
            quantity=order_dict.get("quantity", 0.0),
            price=order_dict.get("price", 0.0),
        )

        # 提交订单
        order_id = self._manager.submit(order)
        logger.info(
            f"订单已提交: {order_id} {order_dict.get('symbol')} {order_dict.get('side')} {order_dict.get('quantity')}"
        )
        return order_id

    def cancel_order(self, order_id: str) -> bool:
        """取消订单

        Args:
            order_id: 订单 ID

        Returns:
            是否取消成功
        """
        result = self._manager.cancel(order_id)
        if result:
            logger.info(f"订单已取消: {order_id}")
        else:
            logger.warning(f"订单取消失败: {order_id}")
        return result

    def get_order_status(self, order_id: str) -> dict[str, Any] | None:
        """获取订单状态

        Args:
            order_id: 订单 ID

        Returns:
            订单状态字典，如果订单不存在返回 None
        """
        try:
            status = self._manager.get_order_status(order_id)
            return status
        except Exception as e:
            logger.error(f"获取订单状态失败: {e}")
            return None

    def snapshot(self) -> dict[str, Any]:
        """获取当前状态快照

        Returns:
            包含订单、持仓、余额的快照字典
        """
        return self._manager.snapshot()

    def snapshot_balance(self) -> dict[str, Any]:
        """获取余额快照

        Returns:
            余额字典
        """
        return self._manager.snapshot_balance()

    def snapshot_positions(self) -> dict[str, Any]:
        """获取持仓快照

        Returns:
            持仓字典
        """
        return self._manager.snapshot_positions()

    def active_count(self) -> int:
        """获取活跃订单数量

        Returns:
            活跃订单数量
        """
        return self._manager.active_count()

    def history_count(self) -> int:
        """获取历史订单数量

        Returns:
            历史订单数量
        """
        return self._manager.history_count()

    def deposit(self, currency: str, amount: float) -> None:
        """存入资金

        Args:
            currency: 货币类型（如 "USDT", "BTC"）
            amount: 存入金额
        """
        self._manager.deposit(currency, amount)
        logger.info(f"存入资金: {amount} {currency}")

    def add_fill(
        self,
        order_id: str,
        fill_id: str,
        symbol: str,
        price: float,
        quantity: float,
        fee: float,
        timestamp: int | None = None,
    ) -> None:
        """添加成交记录

        Args:
            order_id: 订单 ID
            fill_id: 成交 ID
            symbol: 交易对符号
            price: 成交价格
            quantity: 成交数量
            fee: 手续费
            timestamp: 时间戳（纳秒）
        """
        self._manager.add_fill(order_id, fill_id, symbol, price, quantity, fee, timestamp)
        logger.info(f"成交记录已添加: {order_id} {symbol} {quantity}@{price}")


class OMSServiceProxy:
    """OMS 服务代理

    当 axon_quant 不可用时提供空实现。
    """

    def __init__(self):
        self._available = AXON_AVAILABLE
        if self._available:
            self._service = OMSService()
        else:
            self._service = None
            logger.warning("axon_quant.oms 不可用，使用空实现")

    @property
    def available(self) -> bool:
        """axon_quant.oms 是否可用"""
        return self._available

    def submit_order(self, order_dict: dict[str, Any]) -> str:
        """提交订单"""
        if not self._available:
            logger.warning("axon_quant.oms 不可用，跳过订单提交")
            return ""
        return self._service.submit_order(order_dict)

    def cancel_order(self, order_id: str) -> bool:
        """取消订单"""
        if not self._available:
            return False
        return self._service.cancel_order(order_id)

    def get_order_status(self, order_id: str) -> dict[str, Any] | None:
        """获取订单状态"""
        if not self._available:
            return None
        return self._service.get_order_status(order_id)

    def snapshot(self) -> dict[str, Any]:
        """获取快照"""
        if not self._available:
            return {}
        return self._service.snapshot()

    def snapshot_balance(self) -> dict[str, Any]:
        """获取余额快照"""
        if not self._available:
            return {}
        return self._service.snapshot_balance()

    def snapshot_positions(self) -> dict[str, Any]:
        """获取持仓快照"""
        if not self._available:
            return {}
        return self._service.snapshot_positions()

    def active_count(self) -> int:
        """获取活跃订单数量"""
        if not self._available:
            return 0
        return self._service.active_count()

    def history_count(self) -> int:
        """获取历史订单数量"""
        if not self._available:
            return 0
        return self._service.history_count()

    def deposit(self, currency: str, amount: float) -> None:
        """存入资金"""
        if not self._available:
            return
        self._service.deposit(currency, amount)

    def add_fill(
        self,
        order_id: str,
        fill_id: str,
        symbol: str,
        price: float,
        quantity: float,
        fee: float,
        timestamp: int | None = None,
    ) -> None:
        """添加成交记录"""
        if not self._available:
            return
        self._service.add_fill(order_id, fill_id, symbol, price, quantity, fee, timestamp)
