"""回测策略模块 — 基于 axon_quant

为事件驱动回测引擎（axon-quant）提供策略基类：
- EventDrivenStrategyConfig: 事件驱动策略配置基类
- EventDrivenStrategy: 事件驱动策略基类（on_start / on_bar / on_stop）
"""

from .event_strategy import (
    EventDrivenStrategy,
    EventDrivenStrategyConfig,
)

__all__ = [
    "EventDrivenStrategy",
]
