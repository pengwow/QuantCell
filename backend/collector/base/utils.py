# 通用工具函数
import time
import asyncio
from functools import wraps
from datetime import datetime, timedelta

import pandas as pd
from loguru import logger


def deco_retry(max_retry: int = 3, delay: float = 1.0):
    """
    重试装饰器，用于处理网络请求等可能失败的操作
    
    :param max_retry: 最大重试次数
    :param delay: 重试间隔时间（秒）
    :return: 装饰后的函数
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for i in range(max_retry):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    logger.warning(f"函数 {func.__name__} 执行失败，第 {i+1}/{max_retry} 次重试: {e}")
                    if i < max_retry - 1:
                        time.sleep(delay)
                    else:
                        raise
        return wrapper
    return decorator


def get_date_range(start_date, end_date):
    """
    获取日期范围列表
    
    :param start_date: 开始日期，格式为'YYYY-MM-DD'
    :param end_date: 结束日期，格式为'YYYY-MM-DD'
    :return: 日期字符串列表
    """
    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d')
    delta = end - start
    return [(start + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(delta.days + 1)]


def async_deco_retry(max_retry: int = 3, delay: float = 1.0):
    """
    异步重试装饰器
    
    :param max_retry: 最大重试次数
    :param delay: 重试间隔时间（秒）
    :return: 装饰后的异步函数
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            for i in range(max_retry):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    logger.warning(f"异步函数 {func.__name__} 执行失败，第 {i+1}/{max_retry} 次重试: {e}")
                    if i < max_retry - 1:
                        await asyncio.sleep(delay)
                    else:
                        raise
        return wrapper
    return decorator


def str_to_timestamp(date_str, unit='ms'):
    """
    将日期字符串转换为时间戳
    
    :param date_str: 日期字符串，格式为'YYYY-MM-DD'或'YYYY-MM-DD HH:MM:SS'
    :param unit: 时间戳单位，可选'ms'（毫秒）或'us'（微秒）
    :return: 时间戳
    """
    if not date_str:
        return None
    
    formats = ['%Y-%m-%d', '%Y-%m-%d %H:%M:%S']
    timestamp = None
    
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            timestamp = dt.timestamp()
            break
        except ValueError:
            continue
    
    if timestamp is None:
        raise ValueError(f"无法解析日期字符串: {date_str}")
    
    if unit == 'ms':
        return int(timestamp * 1000)
    elif unit == 'us':
        return int(timestamp * 1000000)
    else:
        raise ValueError(f"不支持的时间戳单位: {unit}")


def get_interval_minutes(interval):
    """
    获取时间间隔对应的分钟数
    
    :param interval: 时间间隔，如'1m', '1h'等
    :return: 时间间隔对应的分钟数
    """
    interval_map = {
        '1m': 1,
        '3m': 3,
        '5m': 5,
        '15m': 15,
        '30m': 30,
        '1h': 60,
        '2h': 120,
        '4h': 240,
        '6h': 360,
        '8h': 480,
        '12h': 720,
        '1d': 1440,
        '3d': 4320,
        '1w': 10080,
        '1M': 43200
    }
    return interval_map.get(interval, 1)


def get_interval_ms(interval):
    """
    将时间间隔字符串转换为毫秒数
    
    :param interval: 时间间隔，如'1m', '1h'等
    :return: 时间间隔对应的毫秒数
    """
    interval_map = {
        '1m': 60 * 1000,
        '3m': 3 * 60 * 1000,
        '5m': 5 * 60 * 1000,
        '15m': 15 * 60 * 1000,
        '30m': 30 * 60 * 1000,
        '1h': 60 * 60 * 1000,
        '2h': 2 * 60 * 60 * 1000,
        '4h': 4 * 60 * 60 * 1000,
        '6h': 6 * 60 * 60 * 1000,
        '8h': 8 * 60 * 60 * 1000,
        '12h': 12 * 60 * 60 * 1000,
        '1d': 24 * 60 * 60 * 1000,
        '3d': 3 * 24 * 60 * 60 * 1000,
        '1w': 7 * 24 * 60 * 60 * 1000,
        '1M': 30 * 24 * 60 * 60 * 1000
    }
    return interval_map.get(interval, 60 * 1000)  # 默认1分钟


class ProgressBar:
    """进度条工具类"""
    
    def __init__(self, total, desc="Progress"):
        """
        初始化进度条
        
        :param total: 总任务数
        :param desc: 进度条描述
        """
        self.total = total
        self.desc = desc
        self.current = 0
    
    def update(self, step=1):
        """
        更新进度条
        
        :param step: 进度步长
        """
        self.current += step
        progress = (self.current / self.total) * 100
        logger.info(f"{self.desc}: {self.current}/{self.total} ({progress:.2f}%)")
    
    def finish(self):
        """完成进度条"""
        logger.info(f"{self.desc}: 完成 ({self.total}/{self.total})")
