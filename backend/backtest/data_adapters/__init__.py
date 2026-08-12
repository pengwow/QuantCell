"""数据适配器模块 — 将不同数据源类型统一转换为 OHLCV 格式。"""

from .base_adapter import BaseDataAdapter, LoadConfig, AdapterResult
from .factory import DataAdapterFactory

__all__ = [
    "BaseDataAdapter",
    "LoadConfig",
    "AdapterResult",
    "DataAdapterFactory",
]
