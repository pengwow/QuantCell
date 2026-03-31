# -*- coding: utf-8 -*-
"""
统一日志模块

提供全项目统一的日志功能，包括：
- 多种日志级别配置（DEBUG、INFO、WARNING、ERROR、CRITICAL）
- 控制台和文件输出
- 数据库持久化存储
- 异步写入以提高性能
- 结构化日志数据

使用示例：
    from utils.logger import get_logger

    logger = get_logger(__name__)
    logger.debug("调试信息")
    logger.info("普通信息")
    logger.warning("警告信息")
    logger.error("错误信息")
    logger.critical("严重错误")
"""

import sys
import os
import json
import threading
import asyncio
import queue
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, asdict
from contextvars import ContextVar

from loguru import logger as _loguru_logger

# 日志级别枚举
class LogLevel(Enum):
    """日志级别枚举"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

    @classmethod
    def from_string(cls, level: str) -> "LogLevel":
        """从字符串获取日志级别"""
        try:
            return cls(level.upper())
        except ValueError:
            return cls.INFO

    def to_int(self) -> int:
        """转换为整数级别（用于比较）"""
        levels = {
            LogLevel.DEBUG: 10,
            LogLevel.INFO: 20,
            LogLevel.WARNING: 30,
            LogLevel.ERROR: 40,
            LogLevel.CRITICAL: 50,
        }
        return levels.get(self, 20)


# 日志类型枚举
class LogType(Enum):
    """日志类型枚举"""
    SYSTEM = "system"           # 系统日志
    APPLICATION = "application" # 应用日志
    STRATEGY = "strategy"       # 策略日志
    BACKTEST = "backtest"       # 回测日志
    TRADE = "trade"             # 交易日志
    API = "api"                 # API日志
    DATABASE = "database"       # 数据库日志
    EXCEPTION = "exception"     # 异常日志


@dataclass
class LogRecord:
    """日志记录数据结构"""
    timestamp: datetime
    level: str
    message: str
    module: str
    function: str
    line: int
    logger_name: str
    log_type: str
    extra_data: Optional[Dict[str, Any]] = None
    exception_info: Optional[str] = None
    trace_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        if self.extra_data:
            data['extra_data'] = json.dumps(self.extra_data, ensure_ascii=False)
        return data


class DatabaseLogHandler:
    """
    数据库日志处理器

    将日志异步写入数据库，确保高性能和可靠性
    """

    def __init__(self, batch_size: int = 100, flush_interval: float = 5.0):
        """
        初始化数据库日志处理器

        参数：
            batch_size: 批量写入大小
            flush_interval: 自动刷新间隔（秒）
        """
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self._queue: queue.Queue[LogRecord] = queue.Queue()
        self._lock = threading.Lock()
        self._running = False
        self._flush_thread: Optional[threading.Thread] = None
        self._buffer: List[LogRecord] = []

    def start(self) -> None:
        """启动后台刷新线程"""
        if self._running:
            return

        self._running = True
        self._flush_thread = threading.Thread(target=self._flush_loop, daemon=True)
        self._flush_thread.start()

    def stop(self) -> None:
        """停止后台刷新线程"""
        self._running = False
        if self._flush_thread:
            self._flush_thread.join(timeout=10)
        self._flush_buffer()  # 刷新剩余日志

    def emit(self, record: LogRecord) -> None:
        """接收日志记录"""
        self._queue.put(record)

    def _flush_loop(self) -> None:
        """后台刷新循环"""
        import time
        last_flush = time.time()

        while self._running:
            try:
                # 尝试获取日志记录（带超时）
                record = self._queue.get(timeout=0.1)
                self._buffer.append(record)

                # 检查是否需要刷新
                current_time = time.time()
                if (len(self._buffer) >= self.batch_size or
                    current_time - last_flush >= self.flush_interval):
                    self._flush_buffer()
                    last_flush = current_time

            except queue.Empty:
                # 检查是否需要定时刷新
                current_time = time.time()
                if current_time - last_flush >= self.flush_interval and self._buffer:
                    self._flush_buffer()
                    last_flush = current_time

    def _flush_buffer(self) -> None:
        """将缓冲区中的日志写入数据库"""
        if not self._buffer:
            return

        with self._lock:
            records_to_flush = self._buffer.copy()
            self._buffer.clear()

        try:
            self._write_to_database(records_to_flush)
        except Exception as e:
            # 写入失败时，将日志输出到控制台
            print(f"[DatabaseLogHandler] Failed to write logs to database: {e}", file=sys.stderr)
            for record in records_to_flush:
                print(f"[Lost Log] {record.timestamp} {record.level} {record.message}", file=sys.stderr)

    def _write_to_database(self, records: List[LogRecord]) -> None:
        """将日志记录写入数据库"""
        # 延迟导入以避免循环依赖
        try:
            from collector.db.database import SessionLocal, init_database_config
            from collector.db.models import SystemLog

            init_database_config()

            db = SessionLocal()
            try:
                for record in records:
                    log_entry = SystemLog(
                        timestamp=record.timestamp,
                        level=record.level,
                        message=record.message[:4000],  # 限制长度
                        module=record.module[:200],
                        function=record.function[:200],
                        line=record.line,
                        logger_name=record.logger_name[:200],
                        log_type=record.log_type,
                        extra_data=record.extra_data,
                        exception_info=record.exception_info[:4000] if record.exception_info else None,
                        trace_id=record.trace_id[:100] if record.trace_id else None,
                    )
                    db.add(log_entry)
                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()
        except ImportError:
            # 数据库模块未就绪，跳过写入
            pass


class LoggerConfig:
    """日志配置类"""

    # 默认日志格式
    DEFAULT_FORMAT = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{extra[logger_name]}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )

    # 兼容格式（用于全局处理器，支持无logger_name的情况）
    COMPAT_FORMAT = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )

    # 简单日志格式（用于控制台）
    SIMPLE_FORMAT = "<level>{level: <8}</level> | <level>{message}</level>"

    # 默认日志级别
    DEFAULT_LEVEL = LogLevel.INFO

    # 日志文件保留天数
    RETENTION_DAYS = 30

    # 日志文件轮转大小
    ROTATION_SIZE = "50 MB"

    # 是否启用数据库日志
    ENABLE_DATABASE_LOG = True

    # 数据库日志批量大小
    DATABASE_BATCH_SIZE = 100

    # 数据库日志刷新间隔（秒）
    DATABASE_FLUSH_INTERVAL = 5.0


class UnifiedLogger:
    """
    统一日志器

    封装loguru并提供统一的日志接口，支持数据库持久化
    """

    _instance: Optional["UnifiedLogger"] = None
    _lock = threading.Lock()
    _db_handler: Optional[DatabaseLogHandler] = None

    # 上下文变量：跟踪ID
    _trace_id: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)

    def __new__(cls) -> "UnifiedLogger":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        self._loggers: Dict[str, Any] = {}
        self._setup_logger()

    def _setup_logger(self) -> None:
        """配置基础日志器"""
        # 检查是否在 Worker 进程中（通过环境变量判断）
        is_worker_process = os.environ.get('WORKER_ID') is not None

        if is_worker_process:
            # 在 Worker 进程中，不移除已有的处理器（保留 WorkerLogHandler）
            # 只添加控制台和文件处理器
            pass
        else:
            # 在主进程中，移除默认处理器
            _loguru_logger.remove()

        # 获取日志级别
        level = os.environ.get("LOG_LEVEL", "INFO").upper()

        # 添加控制台处理器（使用兼容格式）
        console_format = os.environ.get("LOG_CONSOLE_FORMAT", "default")
        format_str = (LoggerConfig.SIMPLE_FORMAT if console_format == "simple"
                      else LoggerConfig.COMPAT_FORMAT)

        _loguru_logger.add(
            sys.stdout,
            format=format_str,
            level=level,
            colorize=True,
            enqueue=True,
            backtrace=True,
            diagnose=True,
        )

        # 添加文件处理器（使用兼容格式）
        log_file = self._get_default_log_file()
        if log_file:
            _loguru_logger.add(
                log_file,
                format=LoggerConfig.COMPAT_FORMAT,
                level=level,
                rotation=LoggerConfig.ROTATION_SIZE,
                retention=f"{LoggerConfig.RETENTION_DAYS} days",
                encoding="utf-8",
                enqueue=True,
                backtrace=True,
                diagnose=True,
            )

        # 初始化数据库日志处理器
        if LoggerConfig.ENABLE_DATABASE_LOG:
            self._db_handler = DatabaseLogHandler(
                batch_size=LoggerConfig.DATABASE_BATCH_SIZE,
                flush_interval=LoggerConfig.DATABASE_FLUSH_INTERVAL,
            )
            self._db_handler.start()

    def _get_default_log_file(self) -> Optional[str]:
        """获取默认日志文件路径"""
        try:
            backend_path = Path(__file__).resolve().parent.parent
            log_dir = backend_path / "logs"
            log_dir.mkdir(exist_ok=True)
            return str(log_dir / "quantcell_{time:YYYYMMDD}.log")
        except Exception:
            return None

    def get_logger(self, name: str, log_type: LogType = LogType.APPLICATION) -> "LoggerWrapper":
        """
        获取命名日志器

        参数：
            name: 日志器名称（通常使用__name__）
            log_type: 日志类型

        返回：
            LoggerWrapper: 日志包装器实例
        """
        cache_key = f"{name}_{log_type.value}"
        if cache_key not in self._loggers:
            self._loggers[cache_key] = LoggerWrapper(name, log_type, self)
        return self._loggers[cache_key]

    def _emit_to_database(self, record: LogRecord) -> None:
        """发送日志到数据库"""
        if self._db_handler:
            self._db_handler.emit(record)

    @classmethod
    def set_trace_id(cls, trace_id: str) -> None:
        """设置当前上下文的跟踪ID"""
        cls._trace_id.set(trace_id)

    @classmethod
    def get_trace_id(cls) -> Optional[str]:
        """获取当前上下文的跟踪ID"""
        return cls._trace_id.get()

    @classmethod
    def clear_trace_id(cls) -> None:
        """清除当前上下文的跟踪ID"""
        cls._trace_id.set(None)

    def shutdown(self) -> None:
        """关闭日志器，刷新所有待写入的日志"""
        if self._db_handler:
            self._db_handler.stop()


class LoggerWrapper:
    """
    日志包装器

    封装loguru的logger，提供统一的接口并支持数据库持久化
    """

    def __init__(self, name: str, log_type: LogType, unified_logger: UnifiedLogger):
        self.name = name
        self.log_type = log_type
        self._unified_logger = unified_logger
        self._logger = _loguru_logger.bind(logger_name=name)

    def _log(self, level: LogLevel, message: str, extra: Optional[Dict[str, Any]] = None,
             exception: Optional[BaseException] = None) -> None:
        """内部日志方法"""
        import inspect

        # 获取调用者信息
        frame = inspect.currentframe().f_back.f_back  # type: ignore
        module = frame.f_globals["__name__"]  # type: ignore
        function = frame.f_code.co_name  # type: ignore
        line = frame.f_lineno  # type: ignore

        # 构建日志记录
        trace_id = UnifiedLogger.get_trace_id()
        exception_info = None
        if exception:
            import traceback
            exception_info = traceback.format_exception(type(exception), exception, exception.__traceback__)
            exception_info = "".join(exception_info)

        record = LogRecord(
            timestamp=datetime.utcnow(),
            level=level.value,
            message=str(message),
            module=module,
            function=function,
            line=line,
            logger_name=self.name,
            log_type=self.log_type.value,
            extra_data=extra,
            exception_info=exception_info,
            trace_id=trace_id,
        )

        # 输出到loguru，使用 opt(depth=3) 让 loguru 正确显示调用者信息
        # depth=3 表示从 _log -> info/debug/etc -> 实际调用处
        log_method = getattr(self._logger.opt(depth=3), level.value.lower())
        if exception:
            log_method(message)
        else:
            log_method(message)

        # 异步写入数据库
        if LoggerConfig.ENABLE_DATABASE_LOG:
            self._unified_logger._emit_to_database(record)

    def debug(self, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
        """记录DEBUG级别日志"""
        self._log(LogLevel.DEBUG, message, extra)

    def info(self, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
        """记录INFO级别日志"""
        self._log(LogLevel.INFO, message, extra)

    def warning(self, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
        """记录WARNING级别日志"""
        self._log(LogLevel.WARNING, message, extra)

    def error(self, message: str, extra: Optional[Dict[str, Any]] = None,
              exception: Optional[BaseException] = None) -> None:
        """记录ERROR级别日志"""
        self._log(LogLevel.ERROR, message, extra, exception)

    def critical(self, message: str, extra: Optional[Dict[str, Any]] = None,
                 exception: Optional[BaseException] = None) -> None:
        """记录CRITICAL级别日志"""
        self._log(LogLevel.CRITICAL, message, extra, exception)

    def exception(self, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
        """记录异常信息（自动捕获当前异常）"""
        import sys
        exc_info = sys.exc_info()
        if exc_info[0] is not None:
            self._log(LogLevel.ERROR, message, extra, exc_info[1])
        else:
            self.error(message, extra)

    def bind(self, **kwargs) -> "LoggerWrapper":
        """绑定额外上下文信息"""
        new_wrapper = LoggerWrapper(self.name, self.log_type, self._unified_logger)
        new_wrapper._logger = self._logger.bind(**kwargs)
        return new_wrapper


# 全局统一日志器实例
_unified_logger: Optional[UnifiedLogger] = None


def get_logger(name: str, log_type: LogType = LogType.APPLICATION) -> LoggerWrapper:
    """
    获取日志器

    这是获取日志器的统一入口，所有模块都应该使用此函数获取logger

    参数：
        name: 日志器名称，建议使用__name__
        log_type: 日志类型，默认为APPLICATION

    返回：
        LoggerWrapper: 日志包装器实例

    使用示例：
        from utils.logger import get_logger, LogType

        logger = get_logger(__name__, LogType.API)
        logger.info("API请求处理完成")
        logger.error("处理失败", exception=e)
    """
    global _unified_logger
    if _unified_logger is None:
        _unified_logger = UnifiedLogger()
    return _unified_logger.get_logger(name, log_type)


def set_log_level(level: str) -> None:
    """
    设置全局日志级别

    参数：
        level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    _loguru_logger.remove()
    _loguru_logger.add(
        sys.stdout,
        format=LoggerConfig.DEFAULT_FORMAT,
        level=level.upper(),
        colorize=True,
        enqueue=True,
    )


def set_trace_id(trace_id: str) -> None:
    """设置当前请求的跟踪ID"""
    UnifiedLogger.set_trace_id(trace_id)


def get_trace_id() -> Optional[str]:
    """获取当前请求的跟踪ID"""
    return UnifiedLogger.get_trace_id()


def clear_trace_id() -> None:
    """清除当前请求的跟踪ID"""
    UnifiedLogger.clear_trace_id()


def shutdown_logger() -> None:
    """关闭日志器，在应用退出时调用"""
    global _unified_logger
    if _unified_logger:
        _unified_logger.shutdown()
        _unified_logger = None


class StrategyLogger:
    """
    策略专用日志器（兼容旧接口）

    为策略提供独立的日志记录功能，自动标记策略名称
    """

    # 策略日志目录
    LOG_DIR = Path(__file__).resolve().parent.parent / "logs" / "strategies"

    # 类级别的logger缓存
    _loggers: Dict[str, "StrategyLogger"] = {}

    def __new__(cls, strategy_name: str):
        if strategy_name not in cls._loggers:
            instance = super().__new__(cls)
            instance._initialized = False
            cls._loggers[strategy_name] = instance
        return cls._loggers[strategy_name]

    def __init__(self, strategy_name: str):
        if getattr(self, '_initialized', False):
            return

        self._initialized = True
        self.strategy_name = strategy_name
        self._logger = get_logger(f"strategy.{strategy_name}", LogType.STRATEGY)

        # 确保策略日志目录存在
        self.LOG_DIR.mkdir(parents=True, exist_ok=True)

        # 添加策略专属文件处理器
        log_file = self.LOG_DIR / f"{strategy_name}_{{time:YYYYMMDD}}.log"
        _loguru_logger.add(
            log_file,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
            level="INFO",
            rotation="10 MB",
            retention="7 days",
            encoding="utf-8",
            filter=lambda record: record["extra"].get("logger_name") == f"strategy.{strategy_name}",
        )

    def debug(self, message: str):
        """记录DEBUG级别日志"""
        self._logger.debug(f"[{self.strategy_name}] {message}")

    def info(self, message: str):
        """记录INFO级别日志"""
        self._logger.info(f"[{self.strategy_name}] {message}")

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
    获取策略专用日志器（兼容旧接口）

    参数：
        strategy_name: 策略名称

    返回：
        StrategyLogger: 策略专用日志器
    """
    return StrategyLogger(strategy_name)


# 兼容旧接口：logger 变量
logger = get_logger("default")
