# -*- coding: utf-8 -*-
"""
日志文件读取器 (LogFileReader)

高性能读取 Worker 日志文件，支持：
- 多维度查询（时间范围、级别、关键词）
- 分页查询
- 实时监控（类似 tail -f）
- 日志文件清理与统计

使用示例:
    reader = LogFileReader(log_directory="logs")

    # 查询日志
    logs, total = reader.query_logs(
        worker_id="001",
        level="ERROR",
        start_time=datetime(2026, 4, 28),
        limit=100,
        offset=0,
    )

    # 实时监控
    async for new_log in reader.watch_logs("001"):
        print(new_log)

    # 清理旧日志
    deleted_count = reader.clear_logs("001", before_days=7)
"""

from __future__ import annotations

import os
import re
import asyncio
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Callable, AsyncIterator

from utils.logger import get_logger, LogType

logger = get_logger(__name__, LogType.SYSTEM)


LOG_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.(\d+)Z)\s+\[(\w+)\]\s+\[([^\]]+)\]\s+(.*)$"
)


class LogEntry:
    """日志条目数据类"""

    def __init__(
        self,
        timestamp: datetime,
        level: str,
        source: str,
        message: str,
        raw_line: str,
    ):
        self.timestamp = timestamp
        self.level = level.upper()
        self.source = source
        self.message = message
        self.raw_line = raw_line

    def to_dict(self) -> Dict:
        """转换为字典格式（用于 API 响应）"""
        return {
            "timestamp": self.timestamp.isoformat(),
            "level": self.level,
            "source": self.source,
            "message": self.message,
        }


class LogFileReader:
    """
    日志文件读取器

    职责：
    - 读取 Worker 日志文件（包括轮转备份）
    - 支持多种查询条件过滤
    - 提供实时流式读取能力
    - 管理日志文件的清理和统计
    """

    def __init__(
        self,
        log_directory: Optional[str] = None,
    ):
        """
        初始化日志文件读取器

        Parameters
        ----------
        log_directory : Optional[str]
            日志根目录，默认为项目根目录下的 logs/ 文件夹
        """
        if log_directory is None:
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            log_directory = os.path.join(project_root, "logs")

        self.log_directory = log_directory
        os.makedirs(log_directory, exist_ok=True)

    def _get_log_files(self, worker_id: str) -> List[str]:
        """
        获取 Worker 的所有日志文件（包括轮转备份）

        Parameters
        ----------
        worker_id : str
            Worker ID

        Returns
        -------
        List[str]
            日志文件路径列表（从旧到新排序）
        """
        files = []
        main_file = os.path.join(self.log_directory, f"worker_{worker_id}.log")

        if not os.path.exists(main_file):
            return files

        files.append(main_file)

        for i in range(1, 100):
            backup_file = f"{main_file}.{i}"
            if os.path.exists(backup_file):
                files.append(backup_file)
            else:
                break

        return files

    @staticmethod
    def _parse_line(line: str) -> Optional[LogEntry]:
        """
        解析单行日志文本

        Parameters
        ----------
        line : str
            原始日志行

        Returns
        -------
        Optional[LogEntry]
            解析后的日志条目，无法解析则返回 None
        """
        line = line.strip()
        if not line:
            return None

        match = LOG_PATTERN.match(line)
        if match:
            timestamp_str, microseconds, level, source, message = match.groups()

            try:
                base_timestamp = timestamp_str.rsplit(".", 1)[0]
                timestamp = datetime.fromisoformat(base_timestamp.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                timestamp = datetime.now(timezone.utc)

            return LogEntry(
                timestamp=timestamp,
                level=level,
                source=source,
                message=message,
                raw_line=line,
            )
        else:
            return LogEntry(
                timestamp=datetime.now(timezone.utc),
                level="INFO",
                source="raw",
                message=line,
                raw_line=line,
            )

    def query_logs(
        self,
        worker_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        level: Optional[str] = None,
        keyword: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[Dict], int]:
        """
        查询日志记录

        Parameters
        ----------
        worker_id : str
            Worker ID
        start_time : Optional[datetime]
            开始时间（包含）
        end_time : Optional[datetime]
            结束时间（包含）
        level : Optional[str]
            日志级别过滤（不区分大小写）
        keyword : Optional[str]
            关键词搜索（不区分大小写，在消息内容中匹配）
        limit : int
            返回条数限制（1-1000）
        offset : int
            分页偏移量

        Returns
        -------
        Tuple[List[Dict], int]
            (日志列表, 总数)
        """
        log_files = self._get_log_files(worker_id)
        all_entries: List[LogEntry] = []

        for log_file in reversed(log_files):
            try:
                with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        entry = self._parse_line(line)
                        if entry is None:
                            continue

                        if start_time and entry.timestamp < start_time:
                            continue
                        if end_time and entry.timestamp > end_time:
                            continue
                        if level and entry.level.upper() != level.upper():
                            continue
                        if keyword and keyword.lower() not in entry.message.lower():
                            continue

                        all_entries.append(entry)
            except Exception as e:
                logger.error(f"读取日志文件失败 {log_file}: {e}")

        all_entries.sort(key=lambda x: x.timestamp)  # 正序排列（旧→新，终端风格）

        total = len(all_entries)
        paginated_entries = all_entries[offset : offset + limit]

        return [entry.to_dict() for entry in paginated_entries], total

    def tail_logs(
        self,
        worker_id: str,
        lines: int = 100,
    ) -> List[Dict]:
        """
        获取最新的 N 条日志（类似 `tail -n`）

        Parameters
        ----------
        worker_id : str
            Worker ID
        lines : int
            返回的行数

        Returns
        -------
        List[Dict]
            日志列表（从旧到新排序）
        """
        main_log_file = os.path.join(self.log_directory, f"worker_{worker_id}.log")

        if not os.path.exists(main_log_file):
            return []

        entries: List[Dict] = []

        try:
            with open(main_log_file, "rb") as f:
                f.seek(0, 2)
                file_size = f.tell()

                pos = file_size
                line_count = 0

                while pos > 0 and line_count < lines:
                    pos -= 1
                    f.seek(pos)
                    char = f.read(1)
                    if char == b"\n":
                        line_count += 1

                if line_count >= lines:
                    pos += 1

                f.seek(pos)
                content = f.read().decode("utf-8", errors="ignore")

                for line_content in content.splitlines():
                    entry = self._parse_line(line_content)
                    if entry:
                        entries.append(entry.to_dict())

        except Exception as e:
            logger.error(f"读取日志尾部失败: {e}")

        return entries

    async def watch_logs(
        self,
        worker_id: str,
        callback: Optional[Callable[[Dict], None]] = None,
        poll_interval: float = 0.1,
    ) -> AsyncIterator[Dict]:
        """
        实时监控日志（异步生成器）

        类似 `tail -f`，持续返回新产生的日志。

        Parameters
        ----------
        worker_id : str
            Worker ID
        callback : Optional[Callable[[Dict], None]]
            可选的回调函数，每条新日志都会调用
        poll_interval : float
            轮询间隔（秒），默认 0.1 秒

        Yields
        ------
        Dict
            新的日志条目字典
        """
        main_log_file = os.path.join(self.log_directory, f"worker_{worker_id}.log")

        if os.path.exists(main_log_file):
            file_position = os.path.getsize(main_log_file)
        else:
            file_position = 0

        while True:
            try:
                if os.path.exists(main_log_file):
                    current_size = os.path.getsize(main_log_file)

                    if current_size < file_position:
                        file_position = 0

                    if current_size > file_position:
                        with open(
                            main_log_file, "r", encoding="utf-8", errors="ignore"
                        ) as f:
                            f.seek(file_position)
                            new_content = f.read()
                            file_position = f.tell()

                            for line in new_content.splitlines():
                                entry = self._parse_line(line)
                                if entry:
                                    entry_dict = entry.to_dict()

                                    if callback:
                                        try:
                                            result = callback(entry_dict)
                                            if asyncio.iscoroutine(result):
                                                await result
                                        except Exception as e:
                                            logger.error(f"日志回调错误: {e}")

                                    yield entry_dict
                else:
                    pass

            except Exception as e:
                logger.error(f"监控日志文件错误: {e}")

            await asyncio.sleep(poll_interval)

    def clear_logs(
        self,
        worker_id: str,
        before_days: Optional[int] = None,
    ) -> int:
        """
        清理日志文件

        Parameters
        ----------
        worker_id : str
            Worker ID
        before_days : Optional[int]
            清理多少天前的日志，None 表示清理所有

        Returns
        -------
        int
            删除的文件数
        """
        deleted_count = 0
        log_files = self._get_log_files(worker_id)

        cutoff_time = None
        if before_days is not None:
            cutoff_time = datetime.now(timezone.utc) - timedelta(days=before_days)

        for log_file in log_files:
            try:
                if cutoff_time:
                    mtime = datetime.fromtimestamp(
                        os.path.getmtime(log_file), tz=timezone.utc
                    )
                    if mtime > cutoff_time:
                        continue

                os.remove(log_file)
                deleted_count += 1
                logger.info(f"已删除日志文件: {log_file}")

            except Exception as e:
                logger.error(f"删除日志文件失败 {log_file}: {e}")

        return deleted_count

    def get_log_stats(
        self,
        worker_id: str,
    ) -> Dict:
        """
        获取日志统计信息

        Parameters
        ----------
        worker_id : str
            Worker ID

        Returns
        -------
        Dict
            包含文件列表、总大小、总行数等信息的字典
        """
        stats: Dict = {
            "worker_id": worker_id,
            "files": [],
            "total_size": 0,
            "total_lines": 0,
        }

        log_files = self._get_log_files(worker_id)

        for log_file in log_files:
            try:
                size = os.path.getsize(log_file)
                mtime = datetime.fromtimestamp(
                    os.path.getmtime(log_file), tz=timezone.utc
                )

                if size < 10 * 1024 * 1024:
                    with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                        lines_count = sum(1 for _ in f)
                else:
                    lines_count = size // 200

                file_info: Dict = {
                    "path": log_file,
                    "size": size,
                    "size_human": self._format_size(size),
                    "mtime": mtime.isoformat(),
                    "lines": lines_count,
                }

                stats["files"].append(file_info)
                stats["total_size"] += size
                stats["total_lines"] += lines_count

            except Exception as e:
                logger.error(f"获取日志文件信息失败 {log_file}: {e}")

        stats["total_size_human"] = self._format_size(stats["total_size"])

        return stats

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """
        格式化文件大小为人类可读格式

        Parameters
        ----------
        size_bytes : int
            字节数

        Returns
        -------
        str
            格式化后的大小字符串（如 "15.23 MB"）
        """
        for unit in ["B", "KB", "MB", "GB"]:
            if size_bytes < 1024:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.2f} TB"

    def list_workers_with_logs(self) -> List[str]:
        """
        列出所有有日志文件的 Worker

        Returns
        -------
        List[str]
            Worker ID 列表
        """
        workers = []
        pattern = re.compile(r"^worker_(\d+|[\w-]+)\.log$")

        try:
            for filename in os.listdir(self.log_directory):
                match = pattern.match(filename)
                if match and os.path.isfile(
                    os.path.join(self.log_directory, filename)
                ):
                    workers.append(match.group(1))
        except Exception as e:
            logger.error(f"列出Worker日志失败: {e}")

        return sorted(workers)


class LogFileManager:
    """
    日志文件管理器（单例模式）

    管理所有 Worker 的日志文件，提供全局访问接口。
    """

    _instance: Optional["LogFileManager"] = None

    def __init__(self, log_directory: Optional[str] = None):
        if LogFileManager._instance is not None:
            raise RuntimeError("LogFileManager 是单例，请使用 get_instance()")
        
        self.log_directory = log_directory or os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs"
        )
        self._readers: Dict[str, LogFileReader] = {}

    @classmethod
    def get_instance(cls, log_directory: Optional[str] = None) -> "LogFileManager":
        """
        获取 LogFileManager 单例实例

        Parameters
        ----------
        log_directory : Optional[str]
            日志目录（仅在首次创建时有效）

        Returns
        -------
        LogFileManager
            单例实例
        """
        if cls._instance is None:
            cls._instance = cls(log_directory=log_directory)
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """重置单例（用于测试）"""
        cls._instance = None

    def get_reader(self, worker_id: str) -> LogFileReader:
        """
        获取指定 Worker 的日志读取器

        Parameters
        ----------
        worker_id : str
            Worker ID

        Returns
        -------
        LogFileReader
            日志读取器实例
        """
        if worker_id not in self._readers:
            self._readers[worker_id] = LogFileReader(
                log_directory=self.log_directory
            )
        return self._readers[worker_id]

    def register_worker(self, worker_id: str, log_file_path: str):
        """
        注册 Worker 的日志文件（可选，用于缓存）

        Parameters
        ----------
        worker_id : str
            Worker ID
        log_file_path : str
            日志文件路径
        """
        logger.debug(f"注册Worker日志: {worker_id} -> {log_file_path}")
        self.get_reader(worker_id)

    def unregister_worker(self, worker_id: str):
        """
        注销 Worker（清理缓存）

        Parameters
        ----------
        worker_id : str
            Worker ID
        """
        if worker_id in self._readers:
            del self._readers[worker_id]
            logger.debug(f"注销Worker日志: {worker_id}")

    def list_all_workers(self) -> List[str]:
        """
        列出所有有日志的 Worker

        Returns
        -------
        List[str]
            Worker ID 列表
        """
        reader = LogFileReader(log_directory=self.log_directory)
        return reader.list_workers_with_logs()


def get_log_file_manager() -> LogFileManager:
    """
    便捷函数：获取日志文件管理器单例

    Returns
    -------
    LogFileManager
        全局唯一的日志文件管理器实例
    """
    return LogFileManager.get_instance()


__all__ = [
    "LogFileReader",
    "LogEntry",
    "LogFileManager",
    "get_log_file_manager",
]
