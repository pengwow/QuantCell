# -*- coding: utf-8 -*-
"""
回测引擎模块

提供多种回测引擎实现，支持不同的回测需求。

包含:
    - BacktestEngineBase: 回测引擎抽象基类
    - EngineType: 引擎类型枚举
    - AxonBacktestEngine: 基于 axon_quant 的回测引擎（推荐）
    - Engine: 默认回测引擎（依赖 nautilus_trader）
    - LegacyEngine: 传统回测引擎适配器
    - NautilusBacktestEngine: NautilusTrader 回测引擎（已废弃）

作者: QuantCell Team
版本: 1.1.0
日期: 2026-06-21
"""

__version__ = "1.1.0"
__author__ = "QuantCell Team"

from .base import BacktestEngineBase, EngineType
from .axon_engine import AxonBacktestEngine

# nautilus_trader 相关引擎（可选导入）
try:
    from .engine import Engine
    from .legacy_engine import LegacyEngine
    from .nautilus_engine import NautilusBacktestEngine
    NAUTILUS_AVAILABLE = True
except ImportError:
    NAUTILUS_AVAILABLE = False
    Engine = None
    LegacyEngine = None
    NautilusBacktestEngine = None

__all__ = [
    "BacktestEngineBase",
    "EngineType",
    "AxonBacktestEngine",
    "Engine",
    "LegacyEngine",
    "NautilusBacktestEngine",
    "NAUTILUS_AVAILABLE",
]
