"""
回测引擎模块

包含:
    - BacktestEngineBase: 回测引擎抽象基类
    - EngineType: 引擎类型枚举
    - EventDrivenBacktestEngine: 事件驱动引擎 (axon-quant)

作者: QuantCell Team
版本: 2.0.0
日期: 2026-08-13
"""

__version__ = "2.0.0"
__author__ = "QuantCell Team"

from .base import BacktestEngineBase, EngineType


def __getattr__(name):
    if name == "EventDrivenBacktestEngine":
        from .event_engine import EventDrivenBacktestEngine

        return EventDrivenBacktestEngine
    msg = f"module '{__name__}' has no attribute '{name}'"
    raise AttributeError(msg)


__all__ = [
    "BacktestEngineBase",
    "EngineType",
    "EventDrivenBacktestEngine",
]
