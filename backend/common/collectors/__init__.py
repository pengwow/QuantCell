"""
通用数据采集器模块

提供数据采集的抽象基类和通用工具函数。

主要组件:
    - BaseCollector: 数据采集器抽象基类
    - deco_retry: 重试装饰器
    - async_deco_retry: 异步重试装饰器
    - 日期时间工具函数

使用示例:
    >>> from common.collectors import BaseCollector, deco_retry
    >>> class MyCollector(BaseCollector):
    ...     def get_instrument_list(self):
    ...         return ["BTCUSDT"]

作者: QuantCell Team
版本: 1.0.0
日期: 2026-02-12
"""

from .base import BaseCollector
from .utils import (
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
