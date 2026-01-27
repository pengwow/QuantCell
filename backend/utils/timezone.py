# 时区工具类

import os
from typing import Optional, Union
import datetime
import pytz
from loguru import logger

# 避免循环导入，延迟导入配置
_config_manager = None
_timezone_cache = None


def _get_config_manager():
    """获取配置管理器实例"""
    global _config_manager
    if _config_manager is None:
        from backend.config import config_manager
        _config_manager = config_manager
    return _config_manager


def get_timezone() -> pytz.timezone:
    """获取配置的时区
    
    Returns:
        pytz.timezone: 配置的时区对象
    """
    global _timezone_cache
    
    # 优先从环境变量获取
    timezone_str = os.environ.get("APP_TIMEZONE")
    
    # 如果环境变量未设置，从配置文件获取
    if not timezone_str:
        config_manager = _get_config_manager()
        timezone_str = config_manager.get("app.timezone", "Asia/Shanghai")
    
    # 缓存时区对象
    if _timezone_cache is None or _timezone_cache.zone != timezone_str:
        try:
            _timezone_cache = pytz.timezone(timezone_str)
            logger.info(f"成功加载时区: {timezone_str}")
        except pytz.exceptions.UnknownTimeZoneError:
            logger.error(f"无效的时区配置: {timezone_str}，使用默认时区 Asia/Shanghai")
            _timezone_cache = pytz.timezone("Asia/Shanghai")
    
    return _timezone_cache


def to_local_time(dt: Union[datetime.datetime, None]) -> Union[datetime.datetime, None]:
    """将UTC时间转换为本地时区时间
    
    Args:
        dt: UTC时间对象
    
    Returns:
        datetime.datetime: 本地时区时间对象
    """
    if dt is None:
        return None
    
    try:
        # 如果datetime对象没有时区信息，添加UTC时区
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=pytz.utc)
        
        # 转换为本地时区
        local_tz = get_timezone()
        return dt.astimezone(local_tz)
    except Exception as e:
        logger.error(f"时区转换失败: {e}")
        return dt


def to_utc_time(dt: Union[datetime.datetime, None]) -> Union[datetime.datetime, None]:
    """将本地时区时间转换为UTC时间
    
    Args:
        dt: 本地时区时间对象
    
    Returns:
        datetime.datetime: UTC时间对象
    """
    if dt is None:
        return None
    
    try:
        # 如果datetime对象没有时区信息，添加本地时区
        if dt.tzinfo is None:
            local_tz = get_timezone()
            dt = local_tz.localize(dt)
        
        # 转换为UTC时区
        return dt.astimezone(pytz.utc)
    except Exception as e:
        logger.error(f"时区转换失败: {e}")
        return dt


def format_datetime(dt: Union[datetime.datetime, None], format_str: str = "%Y-%m-%d %H:%M:%S") -> Union[str, None]:
    """格式化datetime对象为字符串
    
    Args:
        dt: datetime对象
        format_str: 格式字符串
    
    Returns:
        str: 格式化后的时间字符串
    """
    if dt is None:
        return None
    
    try:
        # 转换为本地时区
        local_dt = to_local_time(dt)
        return local_dt.strftime(format_str)
    except Exception as e:
        logger.error(f"时间格式化失败: {e}")
        return str(dt)


def parse_datetime(dt_str: str, format_str: str = "%Y-%m-%d %H:%M:%S") -> Optional[datetime.datetime]:
    """解析时间字符串为datetime对象
    
    Args:
        dt_str: 时间字符串
        format_str: 格式字符串
    
    Returns:
        datetime.datetime: datetime对象
    """
    if not dt_str:
        return None
    
    try:
        # 解析字符串为datetime对象
        dt = datetime.datetime.strptime(dt_str, format_str)
        
        # 添加本地时区信息
        local_tz = get_timezone()
        return local_tz.localize(dt)
    except Exception as e:
        logger.error(f"时间解析失败: {e}")
        return None


def reload_timezone():
    """重新加载时区配置
    
    当配置变更时调用此函数
    """
    global _timezone_cache
    _timezone_cache = None
    logger.info("时区配置已重新加载")
