"""
Worker 日志工具集

整合日志相关的所有功能模块：
- LogTimezoneParser: 日志时区解析
- LogEntry: 统一的结构化日志条目
- LogRingBuffer: 内存环形缓冲区（实时查询）
- LogFileReader: 磁盘文件读取器（历史查询）
- LogFileManager: 日志文件管理器

使用示例：
    from .log_utils import get_global_buffer, LogFileReader

    # 内存缓冲区
    buffer = get_global_buffer()
    buffer.append(LogEntry(timestamp="...", level="INFO", message="..."))

    # 文件读取
    reader = LogFileReader()
    logs, total = reader.query_logs(worker_id="001", limit=100)
"""

from __future__ import annotations

import asyncio
import collections
import contextlib
import json
import os
import re
import threading
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta, timezone, tzinfo
from typing import (
    TYPE_CHECKING,
    Any,
)

from utils.logger import LogType, get_logger

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable

logger = get_logger(__name__, LogType.SYSTEM)


# =============================================================================
# 时区解析常量与模式 (来自原 log_timezone_parser.py)
# =============================================================================

TIMESTAMP_PATTERNS = [
    re.compile(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{1,9})Z"),
    re.compile(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{1,9})([+-]\d{2}:\d{2})"),
    re.compile(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})Z"),
    re.compile(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})([+-]\d{2}:\d{2})"),
    re.compile(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{1,9})"),
    re.compile(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})"),
    re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{1,6})"),
    re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})"),
]

TZ_INDICATORS = {
    "UTC": UTC,
    "GMT": UTC,
    "CST": timezone(timedelta(hours=8)),
    "CET": timezone(timedelta(hours=1)),
    "EST": timezone(timedelta(hours=-5)),
    "PST": timezone(timedelta(hours=-8)),
    "JST": timezone(timedelta(hours=9)),
    "KST": timezone(timedelta(hours=9)),
}

TZ_TEXT_PATTERN = re.compile(
    r"(?:timezone|tz|时区)[:\s]+([A-Za-z]{3,4}|[+-]\d{2}:\d{2})",
    re.IGNORECASE,
)


# =============================================================================
# 日志行匹配模式 (来自原 log_file_reader.py)
# =============================================================================

LOG_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{1,9}Z)\s+\[(\w+)\]\s+(\S+?):\s*(.*)$")

RAW_TIMESTAMP_PATTERN = re.compile(r"(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|[+-]\d{2}:\d{2})?)")


# =============================================================================
# 统一的 LogEntry 数据类
# =============================================================================


@dataclass
class LogEntry:
    """结构化日志条目（统一格式，同时支持内存缓冲和文件读取场景）"""

    timestamp: str = ""
    level: str = "INFO"
    message: str = ""
    logger: str = ""
    worker_id: str | None = None
    request_id: str | None = None
    module: str | None = None
    function: str | None = None
    line: int | None = None
    extras: dict[str, Any] | None = None
    raw_line: str | None = None
    source: str | None = None


# =============================================================================
# LogTimezoneParser — 日志时区解析器
# =============================================================================


class LogTimezoneParser:
    """
    日志时区解析器

    自动识别日志文件中的时区信息，并提供时间戳解析和转换功能。
    """

    def __init__(self, default_tz: tzinfo | None = None):
        self.default_tz = default_tz or UTC
        self._detected_tz: tzinfo | None = None

    @property
    def detected_timezone(self) -> tzinfo:
        return self._detected_tz or self.default_tz

    def detect_timezone_from_header(self, header_lines: list[str]) -> tzinfo:
        for line in header_lines:
            tz = self._extract_tz_from_text(line)
            if tz:
                self._detected_tz = tz
                return tz
        for line in header_lines:
            tz = self._extract_tz_from_timestamp_suffix(line)
            if tz:
                self._detected_tz = tz
                return tz
        self._detected_tz = self.default_tz
        return self.default_tz

    def detect_timezone_from_lines(self, lines: list[str], sample_count: int = 10) -> tzinfo:
        sample = lines[:sample_count]
        tz_votes: dict[str, int] = {}
        for line in sample:
            for pattern in TIMESTAMP_PATTERNS[:4]:
                match = pattern.match(line.strip())
                if match:
                    groups = match.groups()
                    if len(groups) > 1 and groups[1]:
                        suffix = groups[1]
                        tz_votes[suffix] = tz_votes.get(suffix, 0) + 1
                    elif len(groups) == 1 and "Z" in match.group(0):
                        tz_votes["Z"] = tz_votes.get("Z", 0) + 1
                    break
        if tz_votes:
            most_common = max(tz_votes.items(), key=lambda x: x[1])[0]
            tz = self._parse_tz_suffix(most_common)
            if tz:
                self._detected_tz = tz
                return tz
        if lines:
            return self.detect_timezone_from_header(lines[:sample_count])
        self._detected_tz = self.default_tz
        return self.default_tz

    def parse_timestamp(self, timestamp_str: str, assume_utc: bool = True) -> datetime:
        timestamp_str = timestamp_str.strip()
        for pattern in TIMESTAMP_PATTERNS:
            match = pattern.match(timestamp_str)
            if match:
                groups = match.groups()
                dt_str = groups[0]
                tz_str = groups[1] if len(groups) > 1 else None
                dt = self._parse_datetime_string(dt_str)
                if tz_str == "Z" or (not tz_str and "Z" in timestamp_str):
                    return dt.replace(tzinfo=UTC)
                elif tz_str and tz_str != "Z":
                    tz = self._parse_tz_suffix(tz_str)
                    if tz:
                        return dt.replace(tzinfo=tz)
                elif assume_utc:
                    return dt.replace(tzinfo=UTC)
                else:
                    return dt.replace(tzinfo=self.detected_timezone)
        try:
            dt = datetime.fromisoformat(timestamp_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC) if assume_utc else dt.replace(tzinfo=self.detected_timezone)
            return dt
        except ValueError:
            pass
        msg = f"无法解析时间戳: {timestamp_str}"
        raise ValueError(msg)

    def convert_timezone(self, dt: datetime, target_tz: tzinfo | None = None) -> datetime:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=self.detected_timezone)
        if target_tz is None:
            return dt.astimezone()
        return dt.astimezone(target_tz)

    def parse_and_convert(self, timestamp_str: str, target_tz: tzinfo | None = None) -> datetime:
        dt = self.parse_timestamp(timestamp_str)
        return self.convert_timezone(dt, target_tz)

    def normalize_timestamp(
        self,
        timestamp_str: str,
        target_tz: tzinfo | None = None,
        output_format: str = "iso",
    ) -> str:
        dt = self.parse_and_convert(timestamp_str, target_tz)
        if output_format == "iso":
            return dt.isoformat()
        elif output_format == "local":
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        return dt.isoformat()

    def _extract_tz_from_text(self, text: str) -> tzinfo | None:
        match = TZ_TEXT_PATTERN.search(text)
        if match:
            tz_str = match.group(1).upper()
            if tz_str in TZ_INDICATORS:
                return TZ_INDICATORS[tz_str]
            try:
                if ":" in tz_str:
                    sign = 1 if tz_str[0] == "+" else -1
                    hours, minutes = map(int, tz_str[1:].split(":"))
                    return timezone(timedelta(hours=sign * hours, minutes=sign * minutes))
            except ValueError, IndexError:
                pass
        return None

    def _extract_tz_from_timestamp_suffix(self, line: str) -> tzinfo | None:
        for pattern in TIMESTAMP_PATTERNS[:4]:
            match = pattern.match(line.strip())
            if match:
                groups = match.groups()
                if len(groups) > 1 and groups[1]:
                    return self._parse_tz_suffix(groups[1])
                elif "Z" in match.group(0):
                    return UTC
        return None

    @staticmethod
    def _parse_tz_suffix(suffix: str) -> tzinfo | None:
        if suffix == "Z":
            return UTC
        match = re.match(r"([+-])(\d{2}):(\d{2})", suffix)
        if match:
            sign = 1 if match.group(1) == "+" else -1
            hours = int(match.group(2))
            minutes = int(match.group(3))
            return timezone(timedelta(hours=sign * hours, minutes=sign * minutes))
        upper = suffix.upper()
        if upper in TZ_INDICATORS:
            return TZ_INDICATORS[upper]
        return None

    @staticmethod
    def _parse_datetime_string(dt_str: str) -> datetime:
        dt_str = dt_str.replace(" ", "T")
        try:
            return datetime.fromisoformat(dt_str)
        except ValueError:
            pass
        formats = [
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%d %H:%M:%S",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(dt_str, fmt)
            except ValueError:
                continue
        msg = f"无法解析日期时间字符串: {dt_str}"
        raise ValueError(msg)


# =============================================================================
# LogRingBuffer — 内存环形缓冲区
# =============================================================================


class LogRingBuffer:
    MAX_ENTRIES = 10000

    def __init__(self, max_entries: int = MAX_ENTRIES):
        self._buffer: collections.deque = collections.deque(maxlen=max_entries)
        self._lock = threading.RLock()
        self.maxlen = max_entries
        self._stats = {
            "total_appended": 0,
            "total_evicted": 0,
            "last_timestamp": None,
            "level_distribution": {},
        }

    def append(self, entry: LogEntry) -> None:
        with self._lock:
            prev_len = len(self._buffer)
            self._buffer.append(entry)
            self._stats["total_appended"] += 1
            self._stats["last_timestamp"] = entry.timestamp
            level = entry.level.upper()
            self._stats["level_distribution"][level] = self._stats["level_distribution"].get(level, 0) + 1
            if prev_len == self.maxlen:
                self._stats["total_evicted"] += 1

    def append_from_dict(self, data: dict[str, Any]) -> None:
        entry = LogEntry(
            timestamp=data.get("timestamp", datetime.now().isoformat()),
            level=data.get("level", "INFO"),
            logger=data.get("logger", ""),
            message=data.get("message", ""),
            worker_id=data.get("worker_id"),
            request_id=data.get("request_id"),
            module=data.get("module"),
            function=data.get("function"),
            line=data.get("line"),
            extras=data.get("extras"),
        )
        self.append(entry)

    def append_raw(
        self,
        message: str,
        level: str = "INFO",
        logger_name: str = "",
        worker_id: str | None = None,
    ) -> None:
        detected_level = level
        if "[ERROR]" in message or "ERROR" in message:
            detected_level = "ERROR"
        elif "[WARN]" in message or "WARNING" in message:
            detected_level = "WARNING"
        elif "[DEBUG]" in message or "DEBUG" in message:
            detected_level = "DEBUG"
        entry = LogEntry(
            timestamp=datetime.now().isoformat(),
            level=detected_level,
            logger=logger_name,
            message=message.strip(),
            worker_id=worker_id,
        )
        self.append(entry)

    def get_recent(
        self,
        limit: int = 100,
        level: str | None = None,
        worker_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        keyword: str | None = None,
    ) -> list[dict[str, Any]]:
        with self._lock:
            entries = list(self._buffer)
        filtered = []
        for entry in entries:
            if level and entry.level.upper() != level.upper():
                continue
            if worker_id and entry.worker_id != worker_id:
                continue
            if start_time:
                try:
                    entry_ts = datetime.fromisoformat(entry.timestamp)
                    if entry_ts < start_time:
                        continue
                except ValueError, TypeError:
                    pass
            if end_time:
                try:
                    entry_ts = datetime.fromisoformat(entry.timestamp)
                    if entry_ts > end_time:
                        continue
                except ValueError, TypeError:
                    pass
            if keyword and keyword.lower() not in entry.message.lower():
                continue
            filtered.append(asdict(entry))
        return filtered[-limit:]

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            current_size = len(self._buffer)
            utilization = round(current_size / self.maxlen * 100, 2) if self.maxlen > 0 else 0
            return {
                **self._stats,
                "current_size": current_size,
                "max_size": self.maxlen,
                "utilization_percent": utilization,
                "remaining_capacity": max(0, self.maxlen - current_size),
            }

    def clear(self) -> None:
        with self._lock:
            cleared_count = len(self._buffer)
            self._buffer.clear()
            self._stats["total_evicted"] += cleared_count
            self._stats["last_timestamp"] = None

    def search(self, query: str, limit: int = 100, case_sensitive: bool = False) -> list[dict[str, Any]]:
        with self._lock:
            entries = list(self._buffer)
        results = []
        for entry in entries:
            text_to_search = f"{entry.message} {entry.logger or ''} {(entry.worker_id or '')}"
            if case_sensitive:
                if query in text_to_search:
                    results.append(asdict(entry))
            else:
                if query.lower() in text_to_search.lower():
                    results.append(asdict(entry))
            if len(results) >= limit:
                break
        return results

    def get_level_counts(self) -> dict[str, int]:
        with self._lock:
            return dict(self._stats["level_distribution"])

    def export_json(self, indent: int = 2) -> str:
        with self._lock:
            entries = [asdict(e) for e in self._buffer]
        return json.dumps(
            {
                "exported_at": datetime.now().isoformat(),
                "total_entries": len(entries),
                "entries": entries,
            },
            indent=indent,
            ensure_ascii=False,
        )


# 全局单例（懒初始化）
_global_buffer: LogRingBuffer | None = None
_buffer_lock = threading.Lock()


def get_global_buffer() -> LogRingBuffer:
    global _global_buffer
    if _global_buffer is None:
        with _buffer_lock:
            if _global_buffer is None:
                _global_buffer = LogRingBuffer()
    return _global_buffer


def reset_global_buffer():
    global _global_buffer
    with _buffer_lock:
        _global_buffer = None


# =============================================================================
# LogFileReader — 磁盘日志文件读取器
# =============================================================================


class LogFileReader:
    """
    日志文件读取器

    职责：读取 Worker 日志文件、多维度查询、实时监控、文件清理统计。
    """

    def __init__(self, log_directory: str | None = None):
        if log_directory is None:
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            log_directory = os.path.join(project_root, "logs", "worker")
        self.log_directory = log_directory
        self.tz_parser = LogTimezoneParser()
        os.makedirs(log_directory, exist_ok=True)

    def _get_log_files(self, worker_id: str) -> list[str]:
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
    def _parse_line(
        line: str,
        tz_parser: LogTimezoneParser | None = None,
        default_timestamp: datetime | None = None,
    ) -> dict[str, Any] | None:
        line = line.strip()
        if not line:
            return None
        if tz_parser is None:
            tz_parser = LogTimezoneParser()

        match = LOG_PATTERN.match(line)
        if match:
            timestamp_str, level, source, message = match.groups()
            try:
                ts = tz_parser.parse_timestamp(timestamp_str)
            except ValueError:
                ts = datetime.now(UTC)
            return asdict(
                LogEntry(
                    timestamp=ts.isoformat(),
                    level=level,
                    message=message,
                    logger=source,
                    raw_line=line,
                    source=source,
                )
            )

        extracted_level = "INFO"
        level_match = re.search(r"\b(DEBUG|INFO|WARN|ERROR)\b", line)
        if level_match:
            extracted_level = level_match.group(1)
        timestamp = default_timestamp or datetime.now(UTC)
        ts_match = RAW_TIMESTAMP_PATTERN.search(line)
        if ts_match:
            with contextlib.suppress(ValueError):
                timestamp = tz_parser.parse_timestamp(ts_match.group(1))
        return asdict(
            LogEntry(
                timestamp=timestamp.isoformat(),
                level=extracted_level,
                message=line,
                raw_line=line,
                source="raw",
            )
        )

    def _detect_timezone(self, worker_id: str) -> None:
        log_files = self._get_log_files(worker_id)
        if not log_files:
            return
        try:
            with open(log_files[0], encoding="utf-8", errors="ignore") as f:
                lines = [f.readline() for _ in range(20)]
                lines = [l for l in lines if l.strip()]
                self.tz_parser.detect_timezone_from_lines(lines)
        except Exception as e:
            logger.warning(f"检测时区失败: {e}")

    def query_logs(
        self,
        worker_id: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        level: str | None = None,
        keyword: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        log_files = self._get_log_files(worker_id)
        all_entries: list[dict] = []
        self._detect_timezone(worker_id)
        last_parsed_ts: datetime | None = None
        for log_file in reversed(log_files):
            try:
                with open(log_file, encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        entry = self._parse_line(line, self.tz_parser, default_timestamp=last_parsed_ts)
                        if entry is None:
                            continue
                        if entry.get("source") != "raw":
                            with contextlib.suppress(ValueError):
                                last_parsed_ts = datetime.fromisoformat(entry["timestamp"])
                        entry_ts = datetime.fromisoformat(entry["timestamp"])
                        if start_time and entry_ts < start_time:
                            continue
                        if end_time and entry_ts > end_time:
                            continue
                        if level and entry["level"].upper() != level.upper():
                            continue
                        if keyword and keyword.lower() not in entry["message"].lower():
                            continue
                        all_entries.append(entry)
            except Exception as e:
                logger.error(f"读取日志文件失败 {log_file}: {e}")
        all_entries.sort(key=lambda x: x["timestamp"])
        total = len(all_entries)
        paginated = all_entries[offset : offset + limit]
        return paginated, total

    def tail_logs(self, worker_id: str, lines: int = 100) -> list[dict]:
        main_log_file = os.path.join(self.log_directory, f"worker_{worker_id}.log")
        if not os.path.exists(main_log_file):
            return []
        self._detect_timezone(worker_id)
        entries: list[dict] = []
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
                    entry = self._parse_line(line_content, self.tz_parser)
                    if entry:
                        entries.append(entry)
        except Exception as e:
            logger.error(f"读取日志尾部失败: {e}")
        return entries

    async def watch_logs(
        self,
        worker_id: str,
        callback: Callable[[dict], None] | None = None,
        poll_interval: float = 0.1,
    ) -> AsyncIterator[dict]:
        main_log_file = os.path.join(self.log_directory, f"worker_{worker_id}.log")
        self._detect_timezone(worker_id)
        file_position = os.path.getsize(main_log_file) if os.path.exists(main_log_file) else 0
        while True:
            try:
                if os.path.exists(main_log_file):
                    current_size = os.path.getsize(main_log_file)
                    if current_size < file_position:
                        file_position = 0
                    if current_size > file_position:
                        with open(main_log_file, encoding="utf-8", errors="ignore") as f:
                            f.seek(file_position)
                            new_content = f.read()
                            file_position = f.tell()
                        for line in new_content.splitlines():
                            entry = self._parse_line(line, self.tz_parser)
                            if entry:
                                if callback:
                                    try:
                                        result = callback(entry)
                                        if asyncio.iscoroutine(result):
                                            await result
                                    except Exception as e:
                                        logger.error(f"日志回调错误: {e}")
                                yield entry
            except Exception as e:
                logger.error(f"监控日志文件错误: {e}")
            await asyncio.sleep(poll_interval)

    def clear_logs(self, worker_id: str, before_days: int | None = None) -> int:
        deleted_count = 0
        log_files = self._get_log_files(worker_id)
        cutoff_time = None
        if before_days is not None:
            cutoff_time = datetime.now(UTC) - timedelta(days=before_days)
        for log_file in log_files:
            try:
                if cutoff_time:
                    mtime = datetime.fromtimestamp(os.path.getmtime(log_file), tz=UTC)
                    if mtime > cutoff_time:
                        continue
                os.remove(log_file)
                deleted_count += 1
                logger.info(f"已删除日志文件: {log_file}")
            except Exception as e:
                logger.error(f"删除日志文件失败 {log_file}: {e}")
        return deleted_count

    def get_log_stats(self, worker_id: str) -> dict:
        stats: dict = {
            "worker_id": worker_id,
            "files": [],
            "total_size": 0,
            "total_lines": 0,
        }
        log_files = self._get_log_files(worker_id)
        for log_file in log_files:
            try:
                size = os.path.getsize(log_file)
                mtime = datetime.fromtimestamp(os.path.getmtime(log_file), tz=UTC)
                if size < 10 * 1024 * 1024:
                    with open(log_file, encoding="utf-8", errors="ignore") as f:
                        lines_count = sum(1 for _ in f)
                else:
                    lines_count = size // 200
                file_info: dict = {
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
        for unit in ["B", "KB", "MB", "GB"]:
            if size_bytes < 1024:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.2f} TB"

    def list_workers_with_logs(self) -> list[str]:
        workers = []
        pattern = re.compile(r"^worker_(\d+|[\w-]+)\.log$")
        try:
            for filename in os.listdir(self.log_directory):
                match = pattern.match(filename)
                if match and os.path.isfile(os.path.join(self.log_directory, filename)):
                    workers.append(match.group(1))
        except Exception as e:
            logger.error(f"列出Worker日志失败: {e}")
        return sorted(workers)


# =============================================================================
# LogFileManager — 日志文件管理器（单例）
# =============================================================================


class LogFileManager:
    _instance: LogFileManager | None = None

    def __init__(self, log_directory: str | None = None):
        if LogFileManager._instance is not None:
            msg = "LogFileManager 是单例，请使用 get_instance()"
            raise RuntimeError(msg)
        self.log_directory = log_directory or os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "logs",
            "worker",
        )
        self._readers: dict[str, LogFileReader] = {}

    @classmethod
    def get_instance(cls, log_directory: str | None = None) -> LogFileManager:
        if cls._instance is None:
            cls._instance = cls(log_directory=log_directory)
        return cls._instance

    @classmethod
    def reset_instance(cls):
        cls._instance = None

    def get_reader(self, worker_id: str) -> LogFileReader:
        if worker_id not in self._readers:
            self._readers[worker_id] = LogFileReader(log_directory=self.log_directory)
        return self._readers[worker_id]

    def register_worker(self, worker_id: str, log_file_path: str):
        logger.debug(f"注册Worker日志: {worker_id} -> {log_file_path}")
        self.get_reader(worker_id)

    def unregister_worker(self, worker_id: str):
        if worker_id in self._readers:
            del self._readers[worker_id]
            logger.debug(f"注销Worker日志: {worker_id}")

    def list_all_workers(self) -> list[str]:
        reader = LogFileReader(log_directory=self.log_directory)
        return reader.list_workers_with_logs()


def get_log_file_manager() -> LogFileManager:
    return LogFileManager.get_instance()


__all__ = [
    # 正则模式（供测试使用）
    "LOG_PATTERN",
    "RAW_TIMESTAMP_PATTERN",
    "TIMESTAMP_PATTERNS",
    "TZ_INDICATORS",
    # 条目与缓冲
    "LogEntry",
    "LogFileManager",
    # 文件读取
    "LogFileReader",
    "LogRingBuffer",
    # 时区解析
    "LogTimezoneParser",
    "get_global_buffer",
    "get_log_file_manager",
    "reset_global_buffer",
]
