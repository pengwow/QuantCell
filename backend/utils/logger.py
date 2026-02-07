# -*- coding: utf-8 -*-
"""
日志配置模块

提供统一的日志配置功能，包括：
- 日志格式配置
- 日志级别设置
- 文件日志输出
- 控制台日志输出
"""

import sys
import os
from pathlib import Path
from typing import Optional
from loguru import logger


class LogConfig:
    """日志配置类"""
    
    # 默认日志格式
    DEFAULT_FORMAT = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )
    
    # 简单日志格式（用于控制台）
    SIMPLE_FORMAT = "<level>{level: <8}</level> | <level>{message}</level>"
    
    # 默认日志级别
    DEFAULT_LEVEL = "INFO"
    
    # 日志文件保留天数
    RETENTION_DAYS = 7
    
    # 日志文件轮转大小
    ROTATION_SIZE = "10 MB"


def setup_logger(
    level: str = "INFO",
    log_file: Optional[str] = None,
    console_output: bool = True,
    simple_console: bool = False
) -> None:
    """
    配置日志
    
    参数：
        level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: 日志文件路径，None则不写入文件
        console_output: 是否输出到控制台
        simple_console: 控制台是否使用简单格式
    """
    # 移除默认处理器
    logger.remove()
    
    # 添加控制台处理器
    if console_output:
        format_str = LogConfig.SIMPLE_FORMAT if simple_console else LogConfig.DEFAULT_FORMAT
        logger.add(
            sys.stdout,
            format=format_str,
            level=level,
            colorize=True,
            enqueue=True
        )
    
    # 添加文件处理器
    if log_file:
        # 确保日志目录存在
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
        
        logger.add(
            log_file,
            format=LogConfig.DEFAULT_FORMAT,
            level=level,
            rotation=LogConfig.ROTATION_SIZE,
            retention=f"{LogConfig.RETENTION_DAYS} days",
            encoding="utf-8",
            enqueue=True
        )


def get_logger(name: Optional[str] = None):
    """
    获取logger实例
    
    参数：
        name: logger名称，用于标识日志来源
        
    返回：
        logger实例
    """
    if name:
        return logger.bind(name=name)
    return logger


def set_log_level(level: str) -> None:
    """
    设置日志级别
    
    参数：
        level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    logger.remove()
    logger.add(sys.stdout, level=level)


def get_default_log_file() -> str:
    """
    获取默认日志文件路径
    
    返回：
        str: 默认日志文件路径
    """
    backend_path = Path(__file__).resolve().parent.parent
    log_dir = backend_path / "logs"
    log_dir.mkdir(exist_ok=True)
    return str(log_dir / "backtest_cli.log")


class StrategyLogger:
    """
    策略专用日志器
    
    为策略提供独立的日志记录功能，自动标记策略名称
    日志只写入文件，不输出到终端
    
    使用示例：
        logger = StrategyLogger("sma_cross")
        logger.info("金叉信号触发")
        logger.debug(f"当前价格: {price}")
    """
    
    # 策略日志目录
    LOG_DIR = Path(__file__).resolve().parent.parent / "logs" / "strategies"
    
    # 类级别的logger缓存，避免重复创建
    _loggers = {}
    
    def __init__(self, strategy_name: str):
        """
        初始化策略日志器
        
        参数：
            strategy_name: 策略名称，用于标识日志来源
        """
        self.strategy_name = strategy_name
        
        # 确保日志目录存在
        self.LOG_DIR.mkdir(parents=True, exist_ok=True)
        
        # 如果该策略的logger已存在，直接复用
        if strategy_name not in StrategyLogger._loggers:
            # 创建新的logger实例
            from loguru import logger as new_logger
            
            # 移除默认处理器
            new_logger.remove()
            
            # 添加文件处理器（只写文件，不输出控制台）
            log_file = self.LOG_DIR / f"{strategy_name}_{{time:YYYYMMDD}}.log"
            new_logger.add(
                log_file,
                format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
                level="INFO",
                rotation="10 MB",
                retention="7 days",
                encoding="utf-8"
            )
            
            StrategyLogger._loggers[strategy_name] = new_logger
        
        self._logger = StrategyLogger._loggers[strategy_name]
    
    def info(self, message: str):
        """记录INFO级别日志"""
        self._logger.info(f"[{self.strategy_name}] {message}")
    
    def debug(self, message: str):
        """记录DEBUG级别日志"""
        self._logger.debug(f"[{self.strategy_name}] {message}")
    
    def warning(self, message: str):
        """记录WARNING级别日志"""
        self._logger.warning(f"[{self.strategy_name}] {message}")
    
    def error(self, message: str):
        """记录ERROR级别日志"""
        self._logger.error(f"[{self.strategy_name}] {message}")
    
    def critical(self, message: str):
        """记录CRITICAL级别日志"""
        self._logger.critical(f"[{self.strategy_name}] {message}")


def get_strategy_logger(strategy_name: str) -> StrategyLogger:
    """
    获取策略专用日志器
    
    这是获取策略日志器的统一接口，所有策略都应该使用此函数获取logger
    
    参数：
        strategy_name: 策略名称
        
    返回：
        StrategyLogger: 策略专用日志器
        
    使用示例：
        class MyStrategy(StrategyBase):
            def __init__(self, params):
                super().__init__(params)
                self.logger = get_strategy_logger("my_strategy")
                
            def on_bar(self, bar):
                self.logger.info("信号触发")
    """
    return StrategyLogger(strategy_name)
