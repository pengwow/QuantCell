# -*- coding: utf-8 -*-
"""
参数验证工具模块

提供CLI参数验证功能，包括：
- 时间范围格式验证
- 货币对格式验证
- 时间周期验证
- 交易模式验证
"""

from datetime import datetime
from typing import Optional, Tuple, List


# 有效的时间周期列表
VALID_TIMEFRAMES = ['15m', '30m', '1h', '4h', '1d']

# 有效的交易模式列表
VALID_TRADING_MODES = ['spot', 'futures', 'perpetual']


def _split_time_range(time_range: str) -> Tuple[str, str]:
    """
    辅助函数：正确分割时间范围字符串
    
    参数：
        time_range: 时间范围字符串
        
    返回：
        Tuple[str, str]: (开始时间字符串, 结束时间字符串)
        
    异常：
        ValueError: 如果无法正确分割
    """
    # 情况1：包含空格（ISO datetime格式）
    if ' ' in time_range:
        # 找到第一个空格后的'-'
        space_index = time_range.index(' ')
        separator_index = time_range.find('-', space_index)
        if separator_index == -1:
            raise ValueError("无法找到时间范围分隔符")
        start_str = time_range[:separator_index].strip()
        end_str = time_range[separator_index+1:].strip()
        return start_str, end_str
    
    # 情况2：不包含空格
    # 检查第一个'-'前的部分是否是8位数字（YYYYMMDD格式）
    first_dash = time_range.find('-')
    if first_dash == -1:
        raise ValueError("无法找到时间范围分隔符")
    
    first_part = time_range[:first_dash]
    if len(first_part) == 8 and first_part.isdigit():
        # YYYYMMDD格式
        start_str = first_part
        end_str = time_range[first_dash+1:].strip()
        return start_str, end_str
    
    # 否则，假设是YYYY-MM-DD格式，找到第三个'-'作为分隔符
    dashes = [i for i, c in enumerate(time_range) if c == '-']
    if len(dashes) < 3:
        raise ValueError("无法找到时间范围分隔符")
    
    separator_index = dashes[2]
    start_str = time_range[:separator_index].strip()
    end_str = time_range[separator_index+1:].strip()
    return start_str, end_str


def validate_time_range(time_range: Optional[str]) -> bool:
    """
    验证时间范围格式（YYYYMMDD-YYYYMMDD 或 ISO格式）
    
    支持格式：
    - YYYYMMDD-YYYYMMDD (例如: 20240101-20241231)
    - YYYY-MM-DD-YYYY-MM-DD (ISO日期格式)
    - YYYY-MM-DD HH:MM:SS-YYYY-MM-DD HH:MM:SS (ISO时间格式)
    
    参数：
        time_range: 时间范围字符串
        
    返回：
        bool: 格式正确返回True，否则返回False
    """
    if not time_range:
        return True  # 允许为空
    
    try:
        start_str, end_str = _split_time_range(time_range)
        
        start_date = None
        end_date = None
        
        # 尝试解析 YYYYMMDD 格式
        try:
            start_date = datetime.strptime(start_str, '%Y%m%d')
            end_date = datetime.strptime(end_str, '%Y%m%d')
        except ValueError:
            # 尝试解析 ISO datetime 格式
            try:
                start_date = datetime.strptime(start_str, '%Y-%m-%d %H:%M:%S')
                end_date = datetime.strptime(end_str, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                # 尝试解析 ISO date 格式
                start_date = datetime.strptime(start_str, '%Y-%m-%d')
                end_date = datetime.strptime(end_str, '%Y-%m-%d')

        if start_date >= end_date:
            return False

        return True
    except Exception:
        return False


def parse_time_range(time_range: Optional[str]) -> Tuple[Optional[datetime], Optional[datetime]]:
    """
    解析时间范围（YYYYMMDD-YYYYMMDD 或 ISO格式）
    
    支持格式：
    - YYYYMMDD-YYYYMMDD (例如: 20240101-20241231)
    - YYYY-MM-DD-YYYY-MM-DD (ISO日期格式)
    - YYYY-MM-DD HH:MM:SS-YYYY-MM-DD HH:MM:SS (ISO时间格式)
    
    参数：
        time_range: 时间范围字符串
        
    返回：
        Tuple[Optional[datetime], Optional[datetime]]: (开始日期, 结束日期)
        
    异常：
        ValueError: 如果时间范围格式错误
    """
    if time_range is None:
        return None, None

    try:
        start_str, end_str = _split_time_range(time_range)
        
        start_date = None
        end_date = None
        
        # 尝试解析 YYYYMMDD 格式
        try:
            start_date = datetime.strptime(start_str, '%Y%m%d')
            end_date = datetime.strptime(end_str, '%Y%m%d')
        except ValueError:
            # 尝试解析 ISO datetime 格式
            try:
                start_date = datetime.strptime(start_str, '%Y-%m-%d %H:%M:%S')
                end_date = datetime.strptime(end_str, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                # 尝试解析 ISO date 格式
                start_date = datetime.strptime(start_str, '%Y-%m-%d')
                end_date = datetime.strptime(end_str, '%Y-%m-%d')

        if start_date >= end_date:
            raise ValueError(f"开始日期必须早于结束日期: {start_date} >= {end_date}")

        return start_date, end_date
    except ValueError as e:
        raise e
    except Exception as e:
        raise ValueError(f"时间范围格式错误: {time_range}，应为 YYYYMMDD-YYYYMMDD 或 ISO格式") from e


def validate_symbols(symbols: Optional[str]) -> bool:
    """
    验证货币对格式
    
    参数：
        symbols: 货币对字符串（逗号分隔）
        
    返回：
        bool: 格式正确返回True，否则返回False
    """
    if not symbols:
        return True  # 允许为空，使用默认值

    symbol_list = symbols.split(',')
    for symbol in symbol_list:
        symbol = symbol.strip()
        if not symbol:  # 允许空字符串
            continue
    return True


def parse_symbols(symbols: Optional[str]) -> List[str]:
    """
    解析货币对字符串为列表
    
    参数：
        symbols: 货币对字符串（逗号分隔）
        
    返回：
        List[str]: 货币对列表
    """
    if not symbols:
        return []
    return [s.strip() for s in symbols.split(',') if s.strip()]


def validate_timeframes(timeframes: Optional[str]) -> bool:
    """
    验证时间周期
    
    参数：
        timeframes: 时间周期字符串（逗号分隔）
        
    返回：
        bool: 周期有效返回True，否则返回False
    """
    if not timeframes:
        return True  # 允许为空，使用默认值

    timeframe_list = timeframes.split(',')

    for timeframe in timeframe_list:
        timeframe = timeframe.strip()
        if timeframe and timeframe not in VALID_TIMEFRAMES:
            return False

    return True


def parse_timeframes(timeframes: Optional[str]) -> List[str]:
    """
    解析时间周期字符串为列表
    
    参数：
        timeframes: 时间周期字符串（逗号分隔）
        
    返回：
        List[str]: 时间周期列表
    """
    if not timeframes:
        return []
    return [t.strip() for t in timeframes.split(',') if t.strip()]


def validate_trading_mode(mode: Optional[str]) -> bool:
    """
    验证交易模式
    
    参数：
        mode: 交易模式字符串
        
    返回：
        bool: 模式有效返回True，否则返回False
    """
    if mode is None:
        return True  # 允许为空，使用默认值
    return mode in VALID_TRADING_MODES


def get_default_values() -> dict:
    """
    获取默认值
    
    返回：
        dict: 包含默认交易模式和时间周期的字典
    """
    return {
        'trading_mode': 'spot',
        'timeframes': ['1h'],
        'symbols': ['BTCUSDT'],
        'init_cash': 100000.0,
        'fees': 0.001,
        'slippage': 0.0001
    }
