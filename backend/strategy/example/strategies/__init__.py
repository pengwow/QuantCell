"""
示例策略模块

包含展示高性能策略执行能力的示例策略：
- VectorizedSMAStrategy: 向量化双均线策略
- ConcurrentPairsStrategy: 并发多交易对策略
- AsyncEventDrivenStrategy: 异步事件驱动策略
"""

from .vectorized_sma import VectorizedSMAStrategy
from .concurrent_pairs import ConcurrentPairsStrategy
from .async_event_driven import AsyncEventDrivenStrategy

__all__ = [
    "VectorizedSMAStrategy",
    "ConcurrentPairsStrategy",
    "AsyncEventDrivenStrategy",
]
