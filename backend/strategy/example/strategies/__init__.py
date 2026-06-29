# -*- coding: utf-8 -*-
"""
示例策略模块（基于 axond 体系）

包含展示 QuantCell 策略框架的示例策略：
- SimpleDualMAStrategy: 简单双均线策略（P3 迁移示例）
- NewStrategy: 多因子综合策略（P3 迁移示例）
- Test0001Strategy: 价格突破策略（P3 迁移示例）
- VectorizedSMAStrategy: 向量化双均线策略（性能示例）
- ConcurrentPairsStrategy: 并发多交易对策略（性能示例）
- AsyncEventDrivenStrategy: 异步事件驱动策略（性能示例）

作者: QuantCell Team
版本: 2.0.0
日期: 2026-06-29
"""

# P3 迁移的标准示例（基于 AxonStrategy）
from .simple_dual_ma import SimpleDualMAStrategy
from .new_strategy import NewStrategy
from .test0001 import Test0001Strategy

# 性能示例策略
from .vectorized_sma import VectorizedSMAStrategy
from .concurrent_pairs import ConcurrentPairsStrategy
from .async_event_driven import AsyncEventDrivenStrategy

__all__ = [
    # P3 迁移的标准示例
    "SimpleDualMAStrategy",
    "NewStrategy",
    "Test0001Strategy",
    # 性能示例
    "VectorizedSMAStrategy",
    "ConcurrentPairsStrategy",
    "AsyncEventDrivenStrategy",
]
