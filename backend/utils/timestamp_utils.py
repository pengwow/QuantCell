"""
时间戳工具模块

提供统一的时间戳处理函数，确保项目内所有时间戳统一为纳秒级精度。

使用规则:
- 数据库存储: 统一使用纳秒级 (19位整数)
- 外部API交互: 根据API要求转换 (通常是毫秒)
- 内部处理: 统一使用纳秒级
- Pandas数据转换: 使用 convert_to_datetime() 自动检测精度（推荐）

核心功能:
1. 精度转换: to_nanoseconds(), from_nanoseconds() - 不同精度间转换
2. 格式化: format_nanoseconds(), parse_to_nanoseconds() - 时间字符串处理
3. Pandas集成: convert_to_datetime() - 智能时间戳→datetime转换（统一入口）
4. 批量处理: batch_to_nanoseconds() - 批量转换
5. 验证: is_valid_nanoseconds(), validate_nanoseconds() - 有效性检查

典型用法:
    # 场景1: Parquet数据加载时自动检测时间戳精度
    from utils.timestamp_utils import convert_to_datetime
    df.index = convert_to_datetime(df.index)  # 自动识别 s/ms/us/ns

    # 场景2: 显式指定精度
    dt = convert_to_datetime(timestamp, precision='ms')

    # 场景3: 纳秒级标准化存储
    from utils.timestamp_utils import to_nanoseconds
    ns_timestamp = to_nanoseconds(original_timestamp)
"""

from typing import Literal, Optional, Union
from datetime import datetime
import logging

try:
    import pandas as pd
except ImportError:
    pd = None

logger = logging.getLogger(__name__)


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


# ============================================================
# Pandas 集成函数（统一的 timestamp → datetime 转换入口）
# ============================================================

def detect_timestamp_precision(data) -> str:
    """
    智能检测时间戳精度（支持标量和序列输入）

    与 detect_precision() 不同之处：
    - 接受 array-like 输入（不仅是标量）
    - 使用统计方法（取第一个有效值）确定整体精度
    - 更健壮的边界值处理
    - 与现有 detect_precision() 保持阈值一致

    Args:
        data: 时间戳数据（标量、Series、Index、array-like）

    Returns:
        str: 检测到的精度 ('s', 'ms', 'us', 'ns', 'unknown')

    Examples:
        >>> detect_timestamp_precision(1776038400000000)  # 16位微秒
        'us'
        >>> import pandas as pd
        >>> detect_timestamp_precision(pd.Series([17760384, 17760393]))  # 10位秒
        's'
    """
    if data is None or (hasattr(data, '__len__') and len(data) == 0):
        return 'unknown'

    try:
        if hasattr(data, 'iloc'):
            first_val = data.iloc[0]
        elif hasattr(data, '__iter__') and not isinstance(data, (str, bytes)):
            first_val = next(iter(data))
        else:
            first_val = data

        if first_val is None or (isinstance(first_val, float) and pd.isna(first_val)):
            return 'unknown'

        return detect_precision(first_val)

    except (ValueError, TypeError, StopIteration) as e:
        logger.debug(f"时间戳精度检测失败: {e}")
        return 'unknown'


def convert_to_datetime(
    data,
    precision: str = 'auto',
    timezone: str = 'utc',
    errors: str = 'coerce',
    validate_year_range: tuple = (2000, 2050)
):
    """
    智能转换时间戳为 datetime（自动检测精度）

    这是项目统一的 pandas 时间戳转换入口，
    替代所有直接调用 pd.to_datetime() 的场景。

    核心特性：
    - 自动检测时间戳精度（s/ms/us/ns）
    - 支持多种输入类型（标量、Series、Index、array-like）
    - 结果合理性验证（年份范围检查）
    - 防御性编程（异常处理和降级策略）
    - 统一的行为和日志记录

    Args:
        data: 输入数据（可以是标量、Series、Index、array-like）
        precision: 时间戳精度 ('auto', 's', 'ms', 'us', 'ns')
                 'auto' 表示根据数值长度自动检测（默认）
        timezone: 时区 ('utc', None表示本地时间）
        errors: 错误处理方式 ('raise', 'coerce')
                'raise' 表示转换失败时抛出异常
                'coerce' 表示转换失败时设为 NaT（默认）
        validate_year_range: 合法年份范围元组 (min_year, max_year)
                            用于验证转换结果的合理性，默认 (2000, 2050)

    Returns:
        转换后的 datetime 对象：
        - 标量输入 → pd.Timestamp
        - Series 输入 → pd.DatetimeIndex
        - Index 输入 → pd.DatetimeIndex
        - 其他序列 → pd.Series

    Raises:
        ValueError: 当 errors='raise' 且转换失败时
        ImportError: 当 pandas 未安装时

    Examples:
        >>> # 16位微秒时间戳自动检测
        >>> convert_to_datetime(1776038400000000)
        Timestamp('2026-04-13 08:00:00+0000', tz='UTC')

        >>> # 序列输入（自动检测为秒级）
        >>> import pandas as pd
        >>> convert_to_datetime([17760384, 17760393])
        DatetimeIndex(['2026-04-13 08:00', '2026-04-13 08:15'],
                     dtype='datetime64[ns, UTC]')

        >>> # DataFrame 列输入
        >>> df = pd.DataFrame({'ts': [17760384, 17760393]})
        >>> convert_to_datetime(df['ts'])
        0   2026-04-13 08:00:00+00:00
        1   2026-04-13 08:15:00+00:00
        Name: ts, dtype: datetime64[ns, UTC]

        >>> # 已经是 datetime 类型，直接返回
        >>> convert_to_datetime(pd.Timestamp('2026-04-13'))
        Timestamp('2026-04-13 00:00:00')

        >>> # 显式指定精度
        >>> convert_to_datetime(17760384, precision='s')
        Timestamp('2026-04-13 08:00:00+0000', tz='UTC')
    """
    if pd is None:
        raise ImportError("pandas 未安装，无法使用 convert_to_datetime()")

    if data is None:
        return pd.NaT

    is_sequence = hasattr(data, '__len__') and not isinstance(data, (str, bytes))

    if is_sequence and len(data) == 0:
        return pd.DatetimeIndex([])

    first_val = _get_first_valid_value(data)

    if first_val is None:
        if is_sequence:
            return pd.DatetimeIndex([])
        return pd.NaT

    if isinstance(first_val, (pd.Timestamp, datetime)):
        logger.debug("输入已经是 datetime 类型，直接转换")
        tz = 'utc' if timezone == 'utc' else None
        result = pd.to_datetime(data, utc=(timezone == 'utc'))
        return result

    detected_precision = precision if precision != 'auto' else detect_timestamp_precision(data)

    if detected_precision == 'unknown':
        logger.warning(f"无法自动检测时间戳精度，使用默认的 pd.to_datetime() 处理")
        try:
            result = pd.to_datetime(data, errors=errors, utc=(timezone == 'utc'))
            return result
        except Exception as e:
            if errors == 'raise':
                raise
            logger.warning(f"时间戳转换失败（降级处理）: {e}")
            if is_sequence:
                return pd.DatetimeIndex([pd.NaT] * len(data))
            return pd.NaT

    logger.debug(f"检测到 {detected_precision} 级时间戳")

    try:
        tz = 'utc' if timezone == 'utc' else None
        result = pd.to_datetime(
            data,
            unit=detected_precision,
            errors=errors,
            utc=bool(tz)
        )

        if is_sequence and len(result) > 0 and hasattr(result, '__getitem__'):
            year = result[0].year
            min_year, max_year = validate_year_range
            if year < min_year or year > max_year:
                logger.warning(
                    f"时间戳转换结果年份可能不正确: year={year}, "
                    f"合理范围=[{min_year}, {max_year}], "
                    f"检测精度={detected_precision}"
                )

        return result

    except (ValueError, TypeError, OverflowError) as e:
        if errors == 'raise':
            raise ValueError(f"时间戳转换失败（precision={detected_precision}）: {e}") from e

        logger.warning(f"时间戳转换失败（{errors}模式）: {e}")

        if is_sequence:
            return pd.DatetimeIndex([pd.NaT] * len(data))
        return pd.NaT


def _get_first_valid_value(data):
    """
    获取数据的第一个有效值（内部辅助函数）

    Args:
        data: 输入数据（任意类型）

    Returns:
        第一个非空值，如果不存在则返回 None
    """
    if data is None:
        return None

    if isinstance(data, (pd.Timestamp, datetime)):
        return data

    try:
        if hasattr(data, 'iloc'):
            for val in data.iloc[:10]:
                if _is_valid_timestamp(val):
                    return val
            return None
        elif hasattr(data, '__iter__') and not isinstance(data, (str, bytes)):
            for val in data:
                if _is_valid_timestamp(val):
                    return val
            return None
        else:
            return data if _is_valid_timestamp(data) else None

    except (TypeError, AttributeError):
        return data


def _is_valid_timestamp(value):
    """
    检查值是否为有效的时间戳（内部辅助函数）

    Args:
        value: 待检查的值

    Returns:
        bool: 是否为有效时间戳
    """
    if value is None:
        return False

    if isinstance(value, float) and pd.isna(value):
        return False

    if isinstance(value, (pd.Timestamp, datetime)):
        return True

    try:
        int(float(value))
        return True
    except (ValueError, TypeError):
        return False




