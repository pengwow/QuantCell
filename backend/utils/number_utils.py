# -*- coding: utf-8 -*-
"""
Number Utilities Module

Provides utility functions for safe numeric conversions with proper error handling.

包含:
    - safe_float: Safely convert values to float with error handling
    - safe_int: Safely convert values to int with error handling
    - safe_decimal: Safely convert values to Decimal with error handling

作者: QuantCell Team
版本: 1.0.0
日期: 2026-02-27
"""

from decimal import Decimal, InvalidOperation
from typing import Any, Optional, Union

from loguru import logger


NumberType = Union[int, float, str, Decimal, None]


def safe_float(value: NumberType, field_name: str = "", default: float = 0.0) -> float:
    """
    Safely convert a value to float with proper error handling.

    This function handles various input types and formats:
    - Strings with commas (e.g., "1,000.50")
    - Numeric values (int, float)
    - Decimal values
    - None or invalid values (returns default)

    Args:
        value: The value to convert. Can be int, float, str, Decimal, or None.
        field_name: Optional name of the field for logging purposes when conversion fails.
        default: Default value to return when conversion fails. Defaults to 0.0.

    Returns:
        float: The converted float value, or default if conversion fails.

    Examples:
        >>> safe_float("1,000.50")
        1000.5
        >>> safe_float("1000.50")
        1000.5
        >>> safe_float(1000)
        1000.0
        >>> safe_float(1000.5)
        1000.5
        >>> safe_float("abc", field_name="price")
        0.0  # Logs warning: "无法转换 price 数值: abc"
        >>> safe_float(None)
        0.0
        >>> safe_float("")
        0.0
        >>> safe_float("invalid", default=-1.0)
        -1.0

    Notes:
        - Commas are treated as thousand separators and removed before conversion
        - Currency symbols or units should be removed before calling this function
        - Invalid conversions are logged as warnings when field_name is provided
    """
    if value is None:
        return default

    if isinstance(value, str):
        # Remove thousand separators (commas) and whitespace
        cleaned = value.replace(",", "").strip()
        if not cleaned:
            return default
        try:
            return float(cleaned)
        except ValueError:
            if field_name:
                logger.warning(f"无法转换 {field_name} 数值: {value}")
            return default

    if isinstance(value, Decimal):
        try:
            return float(value)
        except (ValueError, InvalidOperation):
            if field_name:
                logger.warning(f"无法转换 {field_name} Decimal 数值: {value}")
            return default

    try:
        return float(value)
    except (ValueError, TypeError):
        if field_name:
            logger.warning(f"无法转换 {field_name} 数值: {value}")
        return default


def safe_int(value: NumberType, field_name: str = "", default: int = 0) -> int:
    """
    Safely convert a value to int with proper error handling.

    Args:
        value: The value to convert. Can be int, float, str, Decimal, or None.
        field_name: Optional name of the field for logging purposes when conversion fails.
        default: Default value to return when conversion fails. Defaults to 0.

    Returns:
        int: The converted int value, or default if conversion fails.

    Examples:
        >>> safe_int("1,000")
        1000
        >>> safe_int(1000.7)
        1000  # Truncates decimal part
        >>> safe_int("abc", field_name="count")
        0  # Logs warning: "无法转换 count 数值: abc"
        >>> safe_int(None)
        0

    Notes:
        - Float values are truncated (not rounded)
        - Commas are treated as thousand separators and removed
    """
    if value is None:
        return default

    if isinstance(value, str):
        cleaned = value.replace(",", "").strip()
        if not cleaned:
            return default
        try:
            return int(float(cleaned))
        except ValueError:
            if field_name:
                logger.warning(f"无法转换 {field_name} 数值: {value}")
            return default

    if isinstance(value, Decimal):
        try:
            return int(value)
        except (ValueError, InvalidOperation):
            if field_name:
                logger.warning(f"无法转换 {field_name} Decimal 数值: {value}")
            return default

    try:
        return int(value)
    except (ValueError, TypeError):
        if field_name:
            logger.warning(f"无法转换 {field_name} 数值: {value}")
        return default


def safe_decimal(value: NumberType, field_name: str = "", default: Optional[Decimal] = None) -> Decimal:
    """
    Safely convert a value to Decimal with proper error handling.

    Args:
        value: The value to convert. Can be int, float, str, Decimal, or None.
        field_name: Optional name of the field for logging purposes when conversion fails.
        default: Default value to return when conversion fails. Defaults to Decimal(0).

    Returns:
        Decimal: The converted Decimal value, or default if conversion fails.

    Examples:
        >>> safe_decimal("1,000.50")
        Decimal('1000.50')
        >>> safe_decimal(1000)
        Decimal('1000')
        >>> safe_decimal("abc", field_name="amount")
        Decimal('0')  # Logs warning: "无法转换 amount 数值: abc"
        >>> safe_decimal(None)
        Decimal('0')

    Notes:
        - Use Decimal for financial calculations to avoid floating-point errors
        - Commas are treated as thousand separators and removed
    """
    if default is None:
        default = Decimal(0)

    if value is None:
        return default

    if isinstance(value, Decimal):
        return value

    if isinstance(value, str):
        cleaned = value.replace(",", "").strip()
        if not cleaned:
            return default
        try:
            return Decimal(cleaned)
        except InvalidOperation:
            if field_name:
                logger.warning(f"无法转换 {field_name} 数值: {value}")
            return default

    try:
        return Decimal(str(value))
    except (ValueError, InvalidOperation, TypeError):
        if field_name:
            logger.warning(f"无法转换 {field_name} 数值: {value}")
        return default


def parse_percentage(value: NumberType, field_name: str = "") -> float:
    """
    Parse a percentage value and return as decimal (e.g., 50% -> 0.5).

    Args:
        value: The percentage value. Can include % sign.
        field_name: Optional name of the field for logging purposes.

    Returns:
        float: The percentage as a decimal (0.0 - 1.0), or 0.0 if invalid.

    Examples:
        >>> parse_percentage("50%")
        0.5
        >>> parse_percentage(50)
        0.5
        >>> parse_percentage(0.5)
        0.5
        >>> parse_percentage("0.5")
        0.5
    """
    if isinstance(value, str) and '%' in value:
        value = value.replace('%', '').strip()

    float_val = safe_float(value, field_name, 0.0)

    # If value > 1, assume it's a percentage (e.g., 50 means 50%)
    # If value <= 1, assume it's already a decimal (e.g., 0.5 means 50%)
    if float_val > 1:
        return float_val / 100.0
    return float_val


__all__ = [
    "safe_float",
    "safe_int",
    "safe_decimal",
    "parse_percentage",
]
