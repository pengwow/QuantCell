"""axon_quant.oms 适配层 — 订单管理系统,QuantCell 业务代码唯一入口。

⚠️ 本模块只做直传重导出 + 工厂函数转发,不在 Python 侧实现任何 OMS 逻辑。
axon_quant 0.4.0 暴露:
- 类:   OrderManager / Order / OrderStatus / OrderType / Side
        Portfolio / Position / OmsError
- 工厂: limit_order / market_order / make_order_status
- 枚举: OrderType.{Limit,Market,StopLimit,StopLoss}
        Side.{Buy,Sell}
"""

from axon_quant.oms import (
    # 核心类
    OmsError,
    Order,
    OrderManager,
    OrderStatus,
    OrderType,
    Portfolio,
    Position,
    Side,
    # 工厂
    limit_order,
    make_order_status,
    market_order,
)

__all__ = [
    # 核心类
    "OmsError",
    "Order",
    "OrderManager",
    "OrderStatus",
    "OrderType",
    "Portfolio",
    "Position",
    "Side",
    # 工厂
    "limit_order",
    "make_order_status",
    "market_order",
]
