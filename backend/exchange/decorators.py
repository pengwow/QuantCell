"""
交易所装饰器模块

提供交易所相关的装饰器，如重试、功能检查等。

作者: QuantCell Team
版本: 1.0.0
日期: 2026-02-12
"""

import time
import functools
from typing import Callable, TypeVar, Optional
from loguru import logger

from exchange.exceptions import (
    RateLimitError,
    TemporaryError,
    ConnectionError,
    NotImplementedFeatureError,
)


F = TypeVar("F", bound=Callable[..., any])


def api_retry(
    max_retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: Optional[tuple] = None,
):
    """
    API调用重试装饰器
    
    当指定的异常发生时，自动重试API调用。
    使用指数退避策略增加重试间隔。
    
    Args:
        max_retries: 最大重试次数
        delay: 初始重试延迟（秒）
        backoff: 退避倍数
        exceptions: 需要重试的异常类型元组，默认为 (RateLimitError, TemporaryError, ConnectionError)
    
    Returns:
        装饰器函数
    
    Example:
        @api_retry(max_retries=3, delay=1.0)
        def fetch_data(self):
            return self.api.get_data()
    """
    if exceptions is None:
        exceptions = (RateLimitError, TemporaryError, ConnectionError)
    
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            current_delay = delay
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt == max_retries:
                        logger.error(
                            f"{func.__name__} failed after {max_retries + 1} attempts: {e}"
                        )
                        raise
                    
                    # 如果是RateLimitError且提供了retry_after，使用它
                    if isinstance(e, RateLimitError) and e.retry_after:
                        sleep_time = e.retry_after
                    else:
                        sleep_time = current_delay
                    
                    logger.warning(
                        f"{func.__name__} failed (attempt {attempt + 1}/{max_retries + 1}), "
                        f"retrying in {sleep_time}s: {e}"
                    )
                    time.sleep(sleep_time)
                    current_delay *= backoff
            
            # 不应该到达这里，但为了类型检查
            raise last_exception if last_exception else Exception("Unknown error")
        
        return wrapper
    return decorator


def require_feature(feature: str):
    """
    功能检查装饰器
    
    检查交易所是否支持特定功能，如果不支持则抛出NotImplementedFeatureError。
    
    Args:
        feature: 功能名称，对应_exchange_features字典中的键

    Returns:
        装饰器函数

    Example:
        @require_feature("sub_account")
        def get_sub_accounts(self):
            # 只有支持子账户的交易所才会执行到这里
            pass
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            # 检查交易所是否支持该功能
            if not hasattr(self, '_exchange_features') or not self._exchange_features.get(feature, False):
                exchange_name = getattr(self, 'exchange_name', 'Unknown')
                raise NotImplementedFeatureError(
                    f"Feature '{feature}' is not supported by {exchange_name}",
                    exchange_name=exchange_name,
                    feature=feature,
                )
            return func(self, *args, **kwargs)
        return wrapper
    return decorator


def require_connected(func: F) -> F:
    """
    连接检查装饰器
    
    确保交易所已连接，如果未连接则抛出ConnectionError。
    
    Returns:
        装饰器函数
    
    Example:
        @require_connected
        def get_balance(self):
            # 只有已连接时才会执行到这里
            pass
    """
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        if not getattr(self, '_connected', False):
            exchange_name = getattr(self, 'exchange_name', 'Unknown')
            raise ConnectionError(
                f"Exchange {exchange_name} is not connected. Call connect() first.",
                exchange_name=exchange_name,
            )
        return func(self, *args, **kwargs)
    return wrapper


def log_api_call(level: str = "debug"):
    """
    API调用日志装饰器
    
    记录API调用的入参和出参。
    
    Args:
        level: 日志级别，可选 "debug", "info", "warning", "error"
    
    Returns:
        装饰器函数
    
    Example:
        @log_api_call(level="info")
        def create_order(self, order):
            pass
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            log_func = getattr(logger, level.lower(), logger.debug)
            
            # 记录入参（过滤敏感信息）
            safe_kwargs = {k: v for k, v in kwargs.items() if k not in ['api_key', 'secret_key', 'password']}
            log_func(f"API Call: {func.__name__} args={args[1:]}, kwargs={safe_kwargs}")
            
            try:
                result = func(*args, **kwargs)
                log_func(f"API Success: {func.__name__}")
                return result
            except Exception as e:
                logger.error(f"API Error: {func.__name__} - {e}")
                raise
        
        return wrapper
    return decorator


def rate_limit(calls: int, period: float):
    """
    速率限制装饰器
    
    限制函数的调用频率。
    
    Args:
        calls: 在period时间内允许的最大调用次数
        period: 时间周期（秒）
    
    Returns:
        装饰器函数
    
    Example:
        @rate_limit(calls=10, period=1.0)
        def fetch_data(self):
            pass
    """
    def decorator(func: F) -> F:
        timestamps = []
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            nonlocal timestamps
            
            now = time.time()
            # 清理过期的记录
            timestamps = [t for t in timestamps if now - t < period]
            
            if len(timestamps) >= calls:
                sleep_time = period - (now - timestamps[0])
                if sleep_time > 0:
                    logger.debug(f"Rate limit reached, sleeping for {sleep_time:.2f}s")
                    time.sleep(sleep_time)
            
            timestamps.append(time.time())
            return func(*args, **kwargs)
        
        return wrapper
    return decorator
