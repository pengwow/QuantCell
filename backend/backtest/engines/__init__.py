# -*- coding: utf-8 -*-
"""
回测引擎模块

提供基于 axon_quant 的回测引擎实现。

包含:
    - BacktestEngineBase: 回测引擎抽象基类
    - EngineType: 引擎类型枚举
    - AxonBacktestEngine: 基于 axon_quant 的回测引擎

作者: QuantCell Team
版本: 2.0.0
日期: 2026-06-24
"""

__version__ = "2.0.0"
__author__ = "QuantCell Team"

from .base import BacktestEngineBase, EngineType
from .axon_engine import AxonBacktestEngine
from ..backtest_loop import BacktestLoop, BacktestResult

__all__ = [
    "BacktestEngineBase",
    "EngineType",
    "AxonBacktestEngine",
    "BacktestLoop",
    "BacktestResult",
]
