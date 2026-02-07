# -*- coding: utf-8 -*-
"""
时间解析工具模块

提供时间相关工具函数，包括：
- 时间范围解析
- 日期时间转时间戳
- 时间戳转日期时间
- 格式化日期时间
"""

from datetime import datetime, timedelta
from typing import Optional, Tuple, Union


def parse_time_range(time_range: Optional[str]) -> Tuple[Optional[datetime], Optional[datetime]]:
    """
    解析时间范围（YYYYMMDD-YYYYMMDD）
    
    参数：
        time_range: 时间范围字符串，格式：YYYYMMDD-YYYYMMDD
        
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


def datetime_to_timestamp(dt: datetime, unit: str = 'ms') -> int:
    """
    日期时间转时间戳
    
    参数：
        dt: 日期时间对象
        unit: 时间戳单位，'ms'=毫秒, 's'=秒
        
    返回：
        int: 时间戳
    """
    if unit == 'ms':
        return int(dt.timestamp() * 1000)
    else:
        return int(dt.timestamp())


def timestamp_to_datetime(ts: Union[int, float], unit: str = 'ms') -> datetime:
    """
    时间戳转日期时间
    
    参数：
        ts: 时间戳
        unit: 时间戳单位，'ms'=毫秒, 's'=秒
        
    返回：
        datetime: 日期时间对象
    """
    if unit == 'ms':
        return datetime.fromtimestamp(ts / 1000)
    else:
        return datetime.fromtimestamp(ts)


def format_datetime(dt: datetime, format_str: str = '%Y-%m-%d %H:%M:%S') -> str:
    """
    格式化日期时间
    
    参数：
        dt: 日期时间对象
        format_str: 格式化字符串
        
    返回：
        str: 格式化后的字符串
    """
    return dt.strftime(format_str)


def format_date(dt: datetime, format_str: str = '%Y%m%d') -> str:
    """
    格式化日期
    
    参数：
        dt: 日期时间对象
        format_str: 格式化字符串
        
    返回：
        str: 格式化后的字符串
    """
    return dt.strftime(format_str)


def get_interval_minutes(interval: str) -> int:
    """
    获取时间周期的分钟数
    
    参数：
        interval: 时间周期，如 '15m', '1h', '1d'
        
    返回：
        int: 分钟数
    """
    interval_minutes = {
        '1m': 1,
        '5m': 5,
        '15m': 15,
        '30m': 30,
        '1h': 60,
        '4h': 240,
        '1d': 1440,
        '1w': 10080,
    }
    return interval_minutes.get(interval, 1)


def calculate_expected_klines(start_time: datetime, end_time: datetime, interval: str) -> int:
    """
    计算期望的K线数量
    
    参数：
        start_time: 开始时间
        end_time: 结束时间
        interval: 时间周期
        
    返回：
        int: 期望的K线数量
    """
    minutes = get_interval_minutes(interval)
    time_diff = end_time - start_time
    total_minutes = time_diff.total_seconds() / 60
    return int(total_minutes / minutes) + 1


def align_to_interval(dt: datetime, interval: str) -> datetime:
    """
    将日期时间对齐到时间周期的边界
    
    参数：
        dt: 日期时间对象
        interval: 时间周期
        
    返回：
        datetime: 对齐后的日期时间
    """
    minutes = get_interval_minutes(interval)
    
    if minutes >= 1440:  # 日线及以上
        # 对齐到0点
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        # 对齐到周期边界
        total_minutes = dt.hour * 60 + dt.minute
        aligned_minutes = (total_minutes // minutes) * minutes
        new_hour = aligned_minutes // 60
        new_minute = aligned_minutes % 60
        return dt.replace(hour=new_hour, minute=new_minute, second=0, microsecond=0)


def get_time_range_for_download(start_time: datetime, end_time: datetime, 
                                buffer_days: int = 1) -> Tuple[datetime, datetime]:
    """
    获取下载时间范围（添加缓冲时间）
    
    参数：
        start_time: 开始时间
        end_time: 结束时间
        buffer_days: 缓冲天数
        
    返回：
        Tuple[datetime, datetime]: (缓冲后的开始时间, 缓冲后的结束时间)
    """
    buffered_start = start_time - timedelta(days=buffer_days)
    buffered_end = end_time + timedelta(days=buffer_days)
    return buffered_start, buffered_end
