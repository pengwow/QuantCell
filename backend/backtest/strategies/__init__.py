# -*- coding: utf-8 -*-
"""
回测策略模块

提供回测环境下的策略基类和适配器。

作者: QuantCell Team
版本: 1.0.0
日期: 2026-03-02
"""

# 新的策略适配器（推荐）
from .strategy_adapter import (
    StrategyAdapter,
    StrategyConfig,
    Strategy,  # 别名
)

# 向后兼容：旧的策略基类
from .strategy import (
    Strategy as LegacyStrategy,
    StrategyConfig as LegacyStrategyConfig,
    EventDrivenStrategy,
    EventDrivenStrategyConfig,
)

__all__ = [
    # 新的策略适配器
    "StrategyAdapter",
    "StrategyConfig",
    "Strategy",
    # 向后兼容
    "LegacyStrategy",
    "LegacyStrategyConfig",
    "EventDrivenStrategy",
    "EventDrivenStrategyConfig",
]
