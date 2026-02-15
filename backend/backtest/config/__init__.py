"""
回测引擎配置模块

提供回测引擎的配置管理功能。

包含:
    - EngineType: 引擎类型枚举
    - DEFAULT_ENGINE: 默认引擎类型
    - DEFAULT_CONFIG: 默认引擎配置
    - get_engine_config: 获取引擎配置函数
    - load_engine_config: 加载引擎配置函数

作者: QuantCell Team
版本: 1.0.0
日期: 2026-02-15
"""

__version__ = "1.0.0"
__author__ = "QuantCell Team"

from .settings import EngineType, DEFAULT_ENGINE, DEFAULT_CONFIG
from .engine_config import get_engine_config, load_engine_config

__all__ = [
    "EngineType",
    "DEFAULT_ENGINE",
    "DEFAULT_CONFIG",
    "get_engine_config",
    "load_engine_config",
]
