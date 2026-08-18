"""数据适配器模块 — 将不同数据源类型统一转换为 OHLCV 格式。"""

from .base_adapter import AdapterResult, BaseDataAdapter, LoadConfig
from .factory import DataAdapterFactory

__all__ = [
    "AdapterResult",
    "BaseDataAdapter",
    "DataAdapterFactory",
    "LoadConfig",
]
