# -*- coding: utf-8 -*-
"""
回测引擎模块

提供多种回测引擎实现，支持不同的回测需求。

包含:
    - BacktestEngineBase: 回测引擎抽象基类
    - EngineType: 引擎类型枚举
    - Engine: 默认回测引擎
    - LegacyEngine: 传统回测引擎适配器

作者: QuantCell Team
版本: 1.0.0
日期: 2026-02-15
"""

__version__ = "1.0.0"
__author__ = "QuantCell Team"

from .base import BacktestEngineBase, EngineType
from .engine import Engine
from .legacy_engine import LegacyEngine

__all__ = [
    "BacktestEngineBase",
    "EngineType",
    "Engine",
    "LegacyEngine",
]
