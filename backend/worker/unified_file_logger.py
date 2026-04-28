# -*- coding: utf-8 -*-
"""
统一文件日志器 (UnifiedFileLogger)

捕获所有来源的日志（stdout、logging、loguru、Nautilus），
统一格式化并写入带轮转的日志文件。

使用示例:
    logger = create_unified_logger(
        worker_id="001",
        log_directory="logs",
        max_bytes=100*1024*1024,  # 100MB
        backup_count=10,
    )
    
    logger.install_stdout_capture()
    logger.install_logging_handler()
    logger.install_loguru_sink()
    
    # 所有日志现在会同时输出到终端和 logs/worker_001.log 文件
"""

from __future__ import annotations

import os
import sys
import io
import logging
import re
import threading
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from typing import Optional, TextIO

from utils.logger import get_logger, LogType

logger = get_logger(__name__, LogType.SYSTEM)


class StdoutCapture(io.TextIOWrapper):
    """
    Stdout 捕获器（Tee 模式）

    包装原始 stdout，将所有输出同时写入终端和日志文件。
    """

    def __init__(
        self,
        original_stdout: TextIO,
        unified_logger: "UnifiedFileLogger",
    ):
        self._original_stdout = original_stdout
        self._unified_logger = unified_logger
        super().__init__(original_stdout.buffer, encoding="utf-8", errors="replace")

    def write(self, data: str) -> int:
        """写入数据到原始 stdout 和日志文件"""
        original_write = self._original_stdout.write(data)
        
        if data and self._unified_logger:
            try:
                if "\n" in data or "\r" in data or len(data) > 0:
                    self._unified_logger.write_raw(data)
            except Exception as e:
                pass
        
        return original_write

    def flush(self):
        """刷新缓冲区"""
        try:
            self._original_stdout.flush()
            if self._unified_logger:
                self._unified_logger.flush()
        except Exception:
            pass


class UnifiedFileLogger:
    """
    统一文件日志器

    职责：
    - 捕获所有来源的日志（stdout、logging、loguru、Nautilus）
    - 统一格式化并写入轮转日志文件
    - 高性能缓冲写入（减少 I/O 次数）

    日志格式：
        2026-04-28T10:30:45.123456789Z [INFO] [nautilus.TradingNode] TradingNode started successfully
    """

    NAUTILUS_LOG_PATTERN = re.compile(
        r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z)\s+\[(\w+)\]\s+(.+?):(.*)$"
    )

    def __init__(
        self,
        worker_id: str,
        log_directory: Optional[str] = None,
        max_bytes: int = 100 * 1024 * 1024,  # 默认 100MB
        backup_count: int = 10,
    ):
        """
        初始化统一文件日志器

        Parameters
        ----------
        worker_id : str
            Worker ID
        log_directory : Optional[str]
            日志目录路径，默认为项目根目录下的 logs/ 文件夹
        max_bytes : int
            单个日志文件最大字节数（默认 100MB）
        backup_count : int
            保留的备份文件数（默认 10 个）
        """
        self.worker_id = worker_id
        self.max_bytes = max_bytes
        self.backup_count = backup_count

        if log_directory is None:
            # 获取项目根目录（backend/ 的上级目录）
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            log_directory = os.path.join(project_root, "logs")

        self.log_directory = log_directory
        os.makedirs(log_directory, exist_ok=True)

        self.log_file_path = os.path.join(log_directory, f"worker_{worker_id}.log")

        self._file_handler: Optional[RotatingFileHandler] = None
        self._buffer: list[str] = []
        self._buffer_size: int = 0
        self._max_buffer_size: int = 1024 * 1024  # 1MB 缓冲区
        self._lock: threading.Lock = threading.Lock()

        self._original_stdout = sys.stdout
        self._installed: bool = False

        self._setup_file_handler()

    def _setup_file_handler(self):
        """设置文件 Handler（用于格式化参考）"""
        try:
            self._file_handler = RotatingFileHandler(
                self.log_file_path,
                maxBytes=self.max_bytes,
                backupCount=self.backup_count,
                encoding="utf-8",
            )
            
            formatter = logging.Formatter(
                "%(asctime)s.%(msecs)03dZ [%(levelname)s] [%(name)s] %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
            self._file_handler.setFormatter(formatter)
        except Exception as e:
            logger.error(f"[UnifiedFileLogger] 初始化文件Handler失败: {e}")

    def install_stdout_capture(self):
        """安装 stdout 捕获（Tee 模式）"""
        if self._installed:
            return

        sys.stdout = StdoutCapture(self._original_stdout, self)
        self._installed = True
        logger.info(f"[UnifiedFileLogger] stdout捕获已安装: {self.worker_id}")

    def uninstall_stdout_capture(self):
        """卸载 stdout 捕获"""
        if self._installed and sys.stdout != self._original_stdout:
            sys.stdout = self._original_stdout
            self._installed = False
            logger.info(f"[UnifiedFileLogger] stdout捕获已卸载: {self.worker_id}")

    def install_logging_handler(self):
        """安装 logging 模块 Handler"""
        try:
            root_logger = logging.getLogger()
            
            if self._file_handler and self._file_handler not in root_logger.handlers:
                root_logger.addHandler(self._file_handler)
                
            logger.info(f"[UnifiedFileLogger] logging Handler已安装: {self.worker_id}")
        except Exception as e:
            logger.error(f"[UnifiedFileLogger] 安装logging Handler失败: {e}")

    def uninstall_logging_handler(self):
        """卸载 logging 模块 Handler"""
        try:
            root_logger = logging.getLogger()
            if self._file_handler and self._file_handler in root_logger.handlers:
                root_logger.handlers.remove(self._file_handler)
        except Exception:
            pass

    def install_loguru_sink(self):
        """安装 loguru sink"""
        try:
            from loguru import logger as loguru_logger

            def loguru_sink(message):
                record = message.record
                timestamp_str = record["time"].strftime("%Y-%m-%dT%H:%M:%S.%f")
                log_line = (
                    f"{timestamp_str}Z "
                    f"[{record['level'].name}] "
                    f"[{record['name']}] "
                    f"{message}\n"
                )
                self._write_to_buffer(log_line)

            loguru_logger.add(
                loguru_sink,
                level="DEBUG",
                format="{message}",
            )
            logger.info(f"[UnifiedFileLogger] loguru sink已安装: {self.worker_id}")
        except ImportError:
            logger.warning("[UnifiedFileLogger] loguru未安装，跳过sink安装")
        except Exception as e:
            logger.error(f"[UnifiedFileLogger] 安装loguru sink失败: {e}")

    def write(
        self,
        level: str,
        message: str,
        source: str = "worker",
        timestamp: Optional[datetime] = None,
    ):
        """
        写入结构化日志条目

        Parameters
        ----------
        level : str
            日志级别（DEBUG/INFO/WARNING/ERROR/CRITICAL）
        message : str
            日志消息内容
        source : str
            日志来源标识
        timestamp : Optional[datetime]
            时间戳，默认为当前 UTC 时间
        """
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)

        timestamp_str = (
            timestamp.strftime("%Y-%m-%dT%H:%M:%S.")
            + f"{timestamp.microsecond:06d}Z"
        )

        log_line = f"{timestamp_str} [{level.upper()}] [{source}] {message}\n"
        self._write_to_buffer(log_line)

    def write_raw(self, data: str):
        """
        写入原始数据（用于 stdout 捕获）

        Parameters
        ----------
        data : str
            原始文本数据
        """
        self._write_to_buffer(data)

    def _write_to_buffer(self, data: str):
        """写入缓冲区（带批量刷新优化）"""
        with self._lock:
            self._buffer.append(data)
            self._buffer_size += len(data.encode("utf-8"))

            if self._buffer_size >= self._max_buffer_size or "\n" in data:
                self._flush_buffer()

    def _flush_buffer(self):
        """强制刷新缓冲区到文件"""
        if not self._buffer:
            return

        data = "".join(self._buffer)
        try:
            self._check_and_rotate()

            with open(self.log_file_path, "a", encoding="utf-8") as f:
                f.write(data)

        except Exception as e:
            print(f"[UnifiedFileLogger] 写入失败: {e}", file=self._original_stdout)
        finally:
            self._buffer.clear()
            self._buffer_size = 0

    def _check_and_rotate(self):
        """检查是否需要执行日志轮转"""
        if not os.path.exists(self.log_file_path):
            return

        current_size = os.path.getsize(self.log_file_path)
        if current_size >= self.max_bytes:
            self._do_rollover()

    def _do_rollover(self):
        """执行日志轮转操作"""
        try:
            for i in range(self.backup_count - 1, 0, -1):
                src = f"{self.log_file_path}.{i}"
                dst = f"{self.log_file_path}.{i + 1}"
                if os.path.exists(src):
                    os.rename(src, dst)

            if os.path.exists(self.log_file_path):
                os.rename(self.log_file_path, f"{self.log_file_path}.1")

            logger.debug(
                f"[UnifiedFileLogger] 日志轮转完成: {self.log_file_path}"
            )
        except Exception as e:
            logger.error(f"[UnifiedFileLogger] 日志轮转失败: {e}")

    def get_log_file_path(self) -> str:
        """获取当前日志文件路径"""
        return self.log_file_path

    def get_log_directory(self) -> str:
        """获取日志目录路径"""
        return self.log_directory

    def flush(self):
        """手动刷新缓冲区"""
        self._flush_buffer()

    def close(self):
        """关闭日志器并释放资源"""
        self.flush()

        self.uninstall_stdout_capture()
        self.uninstall_logging_handler()

        if self._file_handler:
            try:
                self._file_handler.close()
            except Exception:
                pass
            self._file_handler = None

        logger.info(f"[UnifiedFileLogger] 已关闭: {self.worker_id}")


def create_unified_logger(
    worker_id: str,
    **kwargs,
) -> UnifiedFileLogger:
    """
    工厂函数：创建统一文件日志器实例

    Parameters
    ----------
    worker_id : str
        Worker ID
    **kwargs
        传递给 UnifiedFileLogger.__init__ 的参数

    Returns
    -------
    UnifiedFileLogger
        统一文件日志器实例
    """
    return UnifiedFileLogger(worker_id=worker_id, **kwargs)


__all__ = [
    "UnifiedFileLogger",
    "StdoutCapture",
    "create_unified_logger",
]
