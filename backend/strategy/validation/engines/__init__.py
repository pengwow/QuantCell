"""
引擎验证模块
包含对事件引擎和向量引擎的特定验证
"""

from ..core.registry import registry

from .event_engine_validator import EventEngineValidator
from .vector_engine_validator import VectorEngineValidator

# 注册引擎验证器
registry.register("event_engine", EventEngineValidator)
registry.register("vector_engine", VectorEngineValidator)

__all__ = [
    "EventEngineValidator",
    "VectorEngineValidator",
]
