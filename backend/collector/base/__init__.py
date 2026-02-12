"""
基础收集器模块（兼容层）

⚠️ 警告：此模块已迁移到 common.collectors
请使用新的导入路径：
    from common.collectors import BaseCollector, deco_retry

此模块保留用于向后兼容，将在未来版本中移除。

作者: QuantCell Team
版本: 1.0.0
日期: 2026-02-12
"""

import warnings

# 发出弃用警告
warnings.warn(
    "collector.base 模块已迁移到 common.collectors，"
    "请更新导入路径。此模块将在未来版本中移除。",
    DeprecationWarning,
    stacklevel=2
)

# 从新的位置重新导出
from common.collectors import (
    BaseCollector,
    ProgressBar,
    async_deco_retry,
    deco_retry,
    get_date_range,
    get_interval_minutes,
    get_interval_ms,
    str_to_timestamp,
)

__all__ = [
    "BaseCollector",
    "deco_retry",
    "async_deco_retry",
    "get_date_range",
    "str_to_timestamp",
    "get_interval_minutes",
    "get_interval_ms",
    "ProgressBar",
]
