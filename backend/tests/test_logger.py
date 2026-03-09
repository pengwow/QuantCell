# -*- coding: utf-8 -*-
"""
日志模块测试

测试统一日志模块的功能
"""

import pytest
import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.logger import (
    get_logger,
    LogLevel,
    LogType,
    LoggerWrapper,
    set_log_level,
    set_trace_id,
    get_trace_id,
    clear_trace_id,
    shutdown_logger,
    get_strategy_logger,
    StrategyLogger,
)


class TestLogLevel:
    """测试日志级别枚举"""

    def test_log_level_values(self):
        """测试日志级别值"""
        assert LogLevel.DEBUG.value == "DEBUG"
        assert LogLevel.INFO.value == "INFO"
        assert LogLevel.WARNING.value == "WARNING"
        assert LogLevel.ERROR.value == "ERROR"
        assert LogLevel.CRITICAL.value == "CRITICAL"

    def test_log_level_from_string(self):
        """测试从字符串创建日志级别"""
        assert LogLevel.from_string("debug") == LogLevel.DEBUG
        assert LogLevel.from_string("INFO") == LogLevel.INFO
        assert LogLevel.from_string("unknown") == LogLevel.INFO  # 默认值

    def test_log_level_to_int(self):
        """测试日志级别转整数"""
        assert LogLevel.DEBUG.to_int() == 10
        assert LogLevel.INFO.to_int() == 20
        assert LogLevel.WARNING.to_int() == 30
        assert LogLevel.ERROR.to_int() == 40
        assert LogLevel.CRITICAL.to_int() == 50


class TestLogType:
    """测试日志类型枚举"""

    def test_log_type_values(self):
        """测试日志类型值"""
        assert LogType.SYSTEM.value == "system"
        assert LogType.APPLICATION.value == "application"
        assert LogType.STRATEGY.value == "strategy"
        assert LogType.BACKTEST.value == "backtest"
        assert LogType.TRADE.value == "trade"
        assert LogType.API.value == "api"
        assert LogType.DATABASE.value == "database"
        assert LogType.EXCEPTION.value == "exception"


class TestLoggerWrapper:
    """测试日志包装器"""

    def test_get_logger(self):
        """测试获取日志器"""
        logger = get_logger("test_module", LogType.APPLICATION)
        assert isinstance(logger, LoggerWrapper)
        assert logger.name == "test_module"
        assert logger.log_type == LogType.APPLICATION

    def test_logger_caching(self):
        """测试日志器缓存"""
        logger1 = get_logger("test_cache", LogType.APPLICATION)
        logger2 = get_logger("test_cache", LogType.APPLICATION)
        # 应该返回同一个实例
        assert logger1 is logger2

    def test_logger_methods(self):
        """测试日志器方法"""
        logger = get_logger("test_methods", LogType.APPLICATION)

        # 测试各个日志级别方法（不实际输出）
        # 这些调用不应该抛出异常
        logger.debug("debug message")
        logger.info("info message")
        logger.warning("warning message")
        logger.error("error message")
        logger.critical("critical message")

    def test_logger_with_extra(self):
        """测试带额外数据的日志"""
        logger = get_logger("test_extra", LogType.APPLICATION)
        extra_data = {"key": "value", "number": 123}

        # 这些调用不应该抛出异常
        logger.info("message with extra", extra=extra_data)
        logger.error("error with extra", extra=extra_data)


class TestTraceId:
    """测试跟踪ID功能"""

    def test_set_get_clear_trace_id(self):
        """测试设置、获取和清除跟踪ID"""
        # 初始状态
        assert get_trace_id() is None

        # 设置跟踪ID
        set_trace_id("test-trace-123")
        assert get_trace_id() == "test-trace-123"

        # 清除跟踪ID
        clear_trace_id()
        assert get_trace_id() is None


class TestStrategyLogger:
    """测试策略日志器"""

    def test_get_strategy_logger(self):
        """测试获取策略日志器"""
        logger = get_strategy_logger("test_strategy")
        assert isinstance(logger, StrategyLogger)
        assert logger.strategy_name == "test_strategy"

    def test_strategy_logger_methods(self):
        """测试策略日志器方法"""
        logger = get_strategy_logger("test_strategy_methods")

        # 这些调用不应该抛出异常
        logger.debug("debug message")
        logger.info("info message")
        logger.warning("warning message")
        logger.error("error message")
        logger.critical("critical message")


class TestLogLevelSetting:
    """测试日志级别设置"""

    def test_set_log_level(self):
        """测试设置日志级别"""
        # 这些调用不应该抛出异常
        set_log_level("DEBUG")
        set_log_level("INFO")
        set_log_level("WARNING")
        set_log_level("ERROR")
        set_log_level("CRITICAL")


class TestLoggerIntegration:
    """测试日志器集成"""

    def test_multiple_loggers(self):
        """测试多个日志器共存"""
        system_logger = get_logger("system_test", LogType.SYSTEM)
        api_logger = get_logger("api_test", LogType.API)
        db_logger = get_logger("db_test", LogType.DATABASE)

        # 每个日志器应该独立工作
        system_logger.info("system message")
        api_logger.info("api message")
        db_logger.info("db message")

    def test_logger_with_exception(self):
        """测试带异常的日志"""
        logger = get_logger("exception_test", LogType.APPLICATION)

        try:
            raise ValueError("test exception")
        except Exception as e:
            # 这些调用不应该抛出异常
            logger.error("error with exception", exception=e)
            logger.critical("critical with exception", exception=e)
            logger.exception("exception message")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
