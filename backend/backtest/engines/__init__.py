# -*- coding: utf-8 -*-
"""
回测引擎模块

提供多种回测引擎实现，支持不同的回测需求。

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
    # 懒加载：EventDrivenBacktestEngine 与 axon-quant 相关，按需导入避免 --help 变慢
    if name == "EventDrivenBacktestEngine":
        from .event_engine import EventDrivenBacktestEngine
        return EventDrivenBacktestEngine
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


__all__ = [
    "BacktestEngineBase",
    "EngineType",
    "EventDrivenBacktestEngine",
]
