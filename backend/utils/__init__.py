# -*- coding: utf-8 -*-
"""
工具模块

提供各种实用工具函数和类
"""

from .decorators import async_deco_retry, deco_retry
from .i18n import get_translation_dict, extract_lang
from .jwt_utils import create_jwt_token, verify_jwt_token
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
    # decorators
    "async_deco_retry",
    "deco_retry",
    # i18n
    "get_translation_dict",
    "extract_lang",
    # jwt_utils
    "create_jwt_token",
    "verify_jwt_token",
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
