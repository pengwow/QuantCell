# -*- coding: utf-8 -*-
"""
工具模块

提供各种实用工具函数和类
"""

from pathlib import Path


def get_backend_root() -> Path:
    """获取后端项目根目录（backend 目录）的绝对路径

    用于构建数据、日志、配置等文件的绝对路径，
    避免因工作目录不同导致的路径解析错误。
    """
    return Path(__file__).resolve().parent.parent


def get_data_dir() -> Path:
    """获取数据根目录: backend/data"""
    return get_backend_root() / "data"


def get_source_data_dir() -> Path:
    """获取源数据目录: backend/data/source"""
    return get_backend_root() / "data" / "source"


from .decorators import async_deco_retry, deco_retry
from .i18n import get_translation_dict, extract_lang
from .jwt_utils import create_jwt_token, verify_jwt_token
from .logger import (
    get_logger,
    get_strategy_logger,
    LogLevel,
    LogType,
    LoggerWrapper,
    set_log_level,
    set_trace_id,
    get_trace_id,
    clear_trace_id,
    shutdown_logger,
)
from .number_utils import (
    safe_float,
    safe_int,
    safe_decimal,
    parse_percentage,
)
from .time_parser import (
    align_to_interval,
    calculate_expected_klines,
    datetime_to_timestamp,
    format_date,
    format_datetime,
    get_date_range,
    get_interval_minutes,
    get_interval_ms,
    get_time_range_for_download,
    parse_time_range,
    str_to_timestamp,
    timestamp_to_datetime,
)
from .timezone import to_utc_time, to_local_time, format_datetime as tz_format_datetime

__all__ = [
    # path utilities
    "get_backend_root",
    "get_data_dir",
    "get_source_data_dir",
    # decorators
    "async_deco_retry",
    "deco_retry",
    # i18n
    "get_translation_dict",
    "extract_lang",
    # jwt_utils
    "create_jwt_token",
    "verify_jwt_token",
    # logger
    "get_logger",
    "get_strategy_logger",
    "LogLevel",
    "LogType",
    "LoggerWrapper",
    "set_log_level",
    "set_trace_id",
    "get_trace_id",
    "clear_trace_id",
    "shutdown_logger",
    # number_utils
    "safe_float",
    "safe_int",
    "safe_decimal",
    "parse_percentage",
    # time_parser
    "align_to_interval",
    "calculate_expected_klines",
    "datetime_to_timestamp",
    "format_date",
    "format_datetime",
    "get_date_range",
    "get_interval_minutes",
    "get_interval_ms",
    "get_time_range_for_download",
    "parse_time_range",
    "str_to_timestamp",
    "timestamp_to_datetime",
    # timezone
    "to_utc_time",
    "to_local_time",
    "tz_format_datetime",
]
