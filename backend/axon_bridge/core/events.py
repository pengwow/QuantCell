"""OrderEvent shim — 等待 axon_quant 0.5+ 真正暴露 OrderEvent 类层级。

axon_quant 0.4.0 不提供 OrderAccepted/OrderCanceled/OrderRejected/OrderFilled
等具体事件类。worker/event_handler.py 期望这些类型做 isinstance 检查,
但目前只能走 duck typing 分支。

本模块提供 4 个占位空类,保证:
1. ``from axon_bridge.core.events import OrderFilled`` 不再抛 ImportError
2. isinstance 检查永远返回 False(占位类无业务实例),行为与 try/except 等价
3. 等 axon_quant 上游真正提供这些类时,把 import 行改为重导出即可,
   worker 业务代码不需要改动
"""


class OrderAccepted:
    """Shim — 等 axon_quant 真正提供时替换为重导出。"""


class OrderCanceled:
    """Shim — 等 axon_quant 真正提供时替换为重导出。"""


class OrderRejected:
    """Shim — 等 axon_quant 真正提供时替换为重导出。"""


class OrderFilled:
    """Shim — 等 axon_quant 真正提供时替换为重导出。"""


__all__ = ["OrderAccepted", "OrderCanceled", "OrderFilled", "OrderRejected"]
