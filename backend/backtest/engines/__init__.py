# -*- coding: utf-8 -*-
"""
回测引擎模块

ponytail: 回测逻辑已统一到 BacktestLoop，BacktestEngine 仅作为向后兼容层。
         新代码应直接使用 backtest.backtest_loop.BacktestLoop。

包含:
    - BacktestEngineBase: 回测引擎抽象基类
    - EngineType: 引擎类型枚举
    - BacktestEngine: 向后兼容层（已废弃，内部委托给 BacktestLoop）
    - BacktestLoop: 统一回测循环入口（推荐使用）
    - BacktestResult: 回测结果数据类

作者: QuantCell Team
版本: 2.1.0
日期: 2026-07-26
"""

import warnings

__version__ = "2.1.0"
__author__ = "QuantCell Team"

from .base import BacktestEngineBase, EngineType
from ..backtest_loop import BacktestLoop, BacktestResult

# BacktestEngine 已废弃，导入时发出警告
warnings.warn(
    "backtest.engines.BacktestEngine 已废弃，请直接使用 BacktestLoop",
    DeprecationWarning,
    stacklevel=2,
)
from .engine import BacktestEngine

__all__ = [
    "BacktestEngineBase",
    "EngineType",
    "BacktestEngine",
    "BacktestLoop",
    "BacktestResult",
]
