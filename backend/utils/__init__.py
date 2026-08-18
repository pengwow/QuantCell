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


from .data_utils import (
    _find_parquet_file,
    _get_default_date_range,
    _normalize_symbol,
    _parse_interval_minutes,
    _ts_to_datetime,
    _validate_parquet_export,
    calculate_data_completeness,
    filter_by_date_range,
    format_completeness,
    format_size,
    format_time_range,
    get_parquet_info,
    load_from_parquet,
    scan_parquet_files,
)
from .decorators import async_deco_retry, deco_retry
from .i18n import extract_lang, get_translation_dict
from .jwt_utils import create_jwt_token, verify_jwt_token
from .logger import (
    LoggerWrapper,
    LogLevel,
    LogType,
    clear_trace_id,
    get_logger,
    get_strategy_logger,
    get_trace_id,
    set_log_level,
    set_trace_id,
    shutdown_logger,
)
from .number_utils import (
    parse_percentage,
    safe_decimal,
    safe_float,
    safe_int,
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
from .timezone import format_datetime as tz_format_datetime
from .timezone import to_local_time, to_utc_time

__all__ = [
    # types
    "LogLevel",
    "LogType",
    "LoggerWrapper",
    # data_utils (parquet tools)
    "_find_parquet_file",
    "_get_default_date_range",
    "_normalize_symbol",
    "_parse_interval_minutes",
    "_ts_to_datetime",
    "_validate_parquet_export",
    # time_parser
    "align_to_interval",
    # decorators
    "async_deco_retry",
    "calculate_data_completeness",
    "calculate_expected_klines",
    "clear_trace_id",
    # jwt_utils
    "create_jwt_token",
    "datetime_to_timestamp",
    "deco_retry",
    "extract_lang",
    "filter_by_date_range",
    "format_completeness",
    "format_date",
    "format_datetime",
    "format_size",
    "format_time_range",
    # path utilities
    "get_backend_root",
    "get_data_dir",
    "get_date_range",
    "get_interval_minutes",
    "get_interval_ms",
    # logger
    "get_logger",
    "get_parquet_info",
    "get_source_data_dir",
    "get_strategy_logger",
    "get_time_range_for_download",
    "get_trace_id",
    # i18n
    "get_translation_dict",
    "load_from_parquet",
    "parse_percentage",
    "parse_time_range",
    # number_utils
    "safe_decimal",
    "safe_float",
    "safe_int",
    "scan_parquet_files",
    "set_log_level",
    "set_trace_id",
    "shutdown_logger",
    "str_to_timestamp",
    "timestamp_to_datetime",
    "to_local_time",
    # timezone
    "to_utc_time",
    "tz_format_datetime",
    "verify_jwt_token",
]
