# -*- coding: utf-8 -*-
"""
回测策略模块

提供回测环境下的策略基类和适配器，基于 axond 体系。

作者: QuantCell Team
版本: 2.0.0
日期: 2026-06-29
"""

# 新的策略适配器（基于 axond 体系）
from .strategy_adapter import (
    StrategyAdapter,
    StrategyConfig,
    Strategy,  # 别名
)

# 事件驱动策略（基于 axond.event_strategy）
from .event_strategy import EventDrivenStrategy

__all__ = [
    # 新的策略适配器
    "StrategyAdapter",
    "StrategyConfig",
    "Strategy",
    # 事件驱动策略
    "EventDrivenStrategy",
]
