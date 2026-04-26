"""
时间戳工具模块

提供统一的时间戳处理函数，确保项目内所有时间戳统一为纳秒级精度。

使用规则:
- 数据库存储: 统一使用纳秒级 (19位整数)
- 外部API交互: 根据API要求转换 (通常是毫秒)
- 内部处理: 统一使用纳秒级
"""

from typing import Literal, Optional, Union
from datetime import datetime


# 时间戳精度类型
Precision = Literal['s', 'ms', 'us', 'ns', 'auto']


def detect_precision(timestamp: Union[str, int]) -> str:
    """
    检测时间戳的精度

    Args:
        timestamp: 时间戳字符串或整数

    Returns:
        str: 's' (秒), 'ms' (毫秒), 'us' (微秒), 'ns' (纳秒)

    Examples:
        >>> detect_precision(1767830400)      # 秒级
        's'
        >>> detect_precision(1767830400000)   # 毫秒级
        'ms'
        >>> detect_precision(1767830400000000)  # 微秒级
        'us'
        >>> detect_precision(1767830400000000000)  # 纳秒级
        'ns'
    """
    ts_int = int(timestamp)

    if ts_int > 10**18:  # 纳秒级 (19位+)
        return 'ns'
    elif ts_int > 10**15:  # 微秒级 (16-18位)
        return 'us'
    elif ts_int > 10**12:  # 毫秒级 (13-15位)
        return 'ms'
    else:  # 秒级 (10位)
        return 's'


def to_nanoseconds(timestamp: Union[str, int, float],
                   input_precision: Precision = 'auto') -> int:
    """
    将任意精度的时间戳转换为纳秒级

    Args:
        timestamp: 输入时间戳
        input_precision: 输入时间戳精度，'auto' 表示自动检测

    Returns:
        int: 纳秒级时间戳

    Raises:
        ValueError: 当时间戳格式无效时

    Examples:
        >>> to_nanoseconds(1767830400)  # 秒级
        1767830400000000000
        >>> to_nanoseconds(1767830400000)  # 毫秒级
        1767830400000000000
        >>> to_nanoseconds(1767830400000000)  # 微秒级
        1767830400000000000
        >>> to_nanoseconds(1767830400000000000)  # 纳秒级
        1767830400000000000
    """
    try:
        ts = int(float(timestamp))
    except (ValueError, TypeError) as e:
        raise ValueError(f"无效的时间戳格式: {timestamp}") from e

    if input_precision == 'auto':
        input_precision = detect_precision(ts)

    if input_precision == 's':
        return ts * 1_000_000_000
    elif input_precision == 'ms':
        return ts * 1_000_000
    elif input_precision == 'us':
        return ts * 1_000
    elif input_precision == 'ns':
        return ts
    else:
        raise ValueError(f"未知的精度类型: {input_precision}")


def from_nanoseconds(timestamp: Union[str, int],
                     output_precision: Precision = 'ns') -> int:
    """
    将纳秒级时间戳转换为指定精度

    Args:
        timestamp: 纳秒级时间戳
        output_precision: 输出精度 ('s', 'ms', 'us', 'ns')

    Returns:
        int: 指定精度的时间戳

    Examples:
        >>> from_nanoseconds(1767830400000000000, 's')
        1767830400
        >>> from_nanoseconds(1767830400000000000, 'ms')
        1767830400000
        >>> from_nanoseconds(1767830400000000000, 'us')
        1767830400000000
        >>> from_nanoseconds(1767830400000000000, 'ns')
        1767830400000000000
    """
    ts = int(timestamp)

    if output_precision == 's':
        return ts // 1_000_000_000
    elif output_precision == 'ms':
        return ts // 1_000_000
    elif output_precision == 'us':
        return ts // 1_000
    elif output_precision == 'ns':
        return ts
    else:
        raise ValueError(f"未知的精度类型: {output_precision}")


def normalize_to_nanoseconds(timestamp: Union[str, int, float],
                             input_precision: Precision = 'auto') -> str:
    """
    标准化时间戳为纳秒级字符串 (用于数据库存储)

    Args:
        timestamp: 输入时间戳
        input_precision: 输入精度

    Returns:
        str: 纳秒级时间戳字符串

    Examples:
        >>> normalize_to_nanoseconds(1767830400)
        '1767830400000000000'
        >>> normalize_to_nanoseconds(1767830400000)
        '1767830400000000000'
    """
    return str(to_nanoseconds(timestamp, input_precision))


def nanoseconds_to_datetime(timestamp: Union[str, int]) -> datetime:
    """
    将纳秒级时间戳转换为datetime对象

    Args:
        timestamp: 纳秒级时间戳

    Returns:
        datetime: datetime对象 (UTC)

    Examples:
        >>> nanoseconds_to_datetime(1767830400000000000)
        datetime.datetime(2026, 1, 8, 0, 0)
    """
    ts = int(timestamp)
    # 纳秒转秒
    seconds = ts / 1_000_000_000
    return datetime.fromtimestamp(seconds)


def datetime_to_nanoseconds(dt: datetime) -> int:
    """
    将datetime对象转换为纳秒级时间戳

    Args:
        dt: datetime对象

    Returns:
        int: 纳秒级时间戳

    Examples:
        >>> from datetime import datetime
        >>> datetime_to_nanoseconds(datetime(2026, 1, 8, 0, 0))
        1767830400000000000
    """
    return int(dt.timestamp() * 1_000_000_000)


def format_nanoseconds(timestamp: Union[str, int],
                       fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """
    将纳秒级时间戳格式化为可读字符串

    Args:
        timestamp: 纳秒级时间戳
        fmt: 格式化字符串

    Returns:
        str: 格式化后的时间字符串

    Examples:
        >>> format_nanoseconds(1767830400000000000)
        '2026-01-08 00:00:00'
    """
    dt = nanoseconds_to_datetime(timestamp)
    return dt.strftime(fmt)


def parse_to_nanoseconds(time_str: str,
                         fmt: str = "%Y-%m-%d %H:%M:%S") -> int:
    """
    将时间字符串解析为纳秒级时间戳

    Args:
        time_str: 时间字符串
        fmt: 格式化字符串

    Returns:
        int: 纳秒级时间戳

    Examples:
        >>> parse_to_nanoseconds("2026-01-08 00:00:00")
        1767830400000000000
    """
    dt = datetime.strptime(time_str, fmt)
    return datetime_to_nanoseconds(dt)


# 便捷函数，用于交易所API交互
def milliseconds_to_nanoseconds(ms: Union[str, int]) -> int:
    """
    毫秒转纳秒 (用于交易所API数据转换)

    Args:
        ms: 毫秒级时间戳

    Returns:
        int: 纳秒级时间戳
    """
    return int(ms) * 1_000_000


def nanoseconds_to_milliseconds(ns: Union[str, int]) -> int:
    """
    纳秒转毫秒 (用于交易所API交互)

    Args:
        ns: 纳秒级时间戳

    Returns:
        int: 毫秒级时间戳
    """
    return int(ns) // 1_000_000


# 批量转换函数
def batch_to_nanoseconds(timestamps: list,
                         input_precision: Precision = 'auto') -> list:
    """
    批量将时间戳转换为纳秒级

    Args:
        timestamps: 时间戳列表
        input_precision: 输入精度

    Returns:
        list: 纳秒级时间戳列表
    """
    return [to_nanoseconds(ts, input_precision) for ts in timestamps]


def batch_normalize_to_nanoseconds(timestamps: list,
                                   input_precision: Precision = 'auto') -> list:
    """
    批量标准化时间戳为纳秒级字符串

    Args:
        timestamps: 时间戳列表
        input_precision: 输入精度

    Returns:
        list: 纳秒级时间戳字符串列表
    """
    return [normalize_to_nanoseconds(ts, input_precision) for ts in timestamps]


# 验证函数
def is_valid_nanoseconds(timestamp: Union[str, int]) -> bool:
    """
    验证是否为有效的纳秒级时间戳

    Args:
        timestamp: 待验证的时间戳

    Returns:
        bool: 是否有效
    """
    try:
        ts = int(timestamp)
        # 纳秒级时间戳应该是19位左右
        # 合理的范围: 2000-01-01 到 2100-01-01
        # 946684800000000000 (2000年) 到 4102444800000000000 (2100年)
        return 10**18 <= ts < 10**19
    except (ValueError, TypeError):
        return False


def validate_nanoseconds(timestamp: Union[str, int],
                         field_name: str = "timestamp") -> None:
    """
    验证纳秒级时间戳，无效时抛出异常

    Args:
        timestamp: 待验证的时间戳
        field_name: 字段名称，用于错误信息

    Raises:
        ValueError: 当时间戳无效时
    """
    if not is_valid_nanoseconds(timestamp):
        raise ValueError(
            f"{field_name} 必须是有效的纳秒级时间戳 (19位整数), "
            f"实际值: {timestamp}"
        )



