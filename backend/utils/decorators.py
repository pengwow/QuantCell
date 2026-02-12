# -*- coding: utf-8 -*-
"""
装饰器工具模块

提供常用的装饰器，包括同步/异步重试装饰器。

主要功能:
    - deco_retry: 同步重试装饰器
    - async_deco_retry: 异步重试装饰器

使用示例:
    >>> from utils.decorators import deco_retry
    >>> @deco_retry(max_retry=3, delay=1.0)
    ... def fetch_data():
    ...     return requests.get(url)

作者: QuantCell Team
版本: 1.0.0
日期: 2026-02-12
"""

import asyncio
import time
from functools import wraps

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
