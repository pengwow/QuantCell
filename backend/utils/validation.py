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


def validate_time_range(time_range: Optional[str]) -> bool:
    """
    验证时间范围格式（YYYYMMDD-YYYYMMDD）
    
    参数：
        time_range: 时间范围字符串
        
    返回：
        bool: 格式正确返回True，否则返回False
    """
    if not time_range:
        return True  # 允许为空
    
    try:
        parts = time_range.split('-')
        if len(parts) != 2:
            return False

        start_date = datetime.strptime(parts[0], '%Y%m%d')
        end_date = datetime.strptime(parts[1], '%Y%m%d')

        if start_date >= end_date:
            return False

        return True
    except ValueError:
        return False


def parse_time_range(time_range: Optional[str]) -> Tuple[Optional[datetime], Optional[datetime]]:
    """
    解析时间范围（YYYYMMDD-YYYYMMDD）
    
    参数：
        time_range: 时间范围字符串
        
    返回：
        Tuple[Optional[datetime], Optional[datetime]]: (开始日期, 结束日期)
        
    异常：
        ValueError: 如果时间范围格式错误
    """
    if time_range is None:
        return None, None

    parts = time_range.split('-')
    if len(parts) != 2:
        raise ValueError(f"时间范围格式错误: {time_range}，应为 YYYYMMDD-YYYYMMDD")

    start_date = datetime.strptime(parts[0], '%Y%m%d')
    end_date = datetime.strptime(parts[1], '%Y%m%d')

    if start_date >= end_date:
        raise ValueError(f"开始日期必须早于结束日期: {start_date} >= {end_date}")

    return start_date, end_date


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
