"""
日志环形缓冲区 - 内存中保留最近的 N 条日志，支持高效查询

核心特性：
1. 固定大小的内存缓冲区（FIFO 淘汰旧条目）
2. 线程安全（适用于多进程/多线程环境）
3. 支持多维度过滤（level, worker_id, time_range, keyword）
4. O(1) 追加，O(n) 查询
5. 统计信息收集

使用场景：
- 实时查看 Worker 运行状态
- 快速定位错误日志
- 开发调试
- API 端点提供实时日志查询

使用示例：
    from .log_ring_buffer import get_global_buffer

    buffer = get_global_buffer()

    # 追加日志
    buffer.append(LogEntry(
        timestamp=datetime.now().isoformat(),
        level="INFO",
        message="Worker started",
        worker_id="001",
    ))

    # 查询最近 50 条 ERROR 日志
    errors = buffer.get_recent(limit=50, level="ERROR")

    # 获取统计信息
    stats = buffer.get_stats()
"""

import collections
import threading
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict


@dataclass
class LogEntry:
    """结构化日志条目"""
    timestamp: str
    level: str
    message: str
    logger: str = ""
    worker_id: Optional[str] = None
    request_id: Optional[str] = None
    module: Optional[str] = None
    function: Optional[str] = None
    line: Optional[int] = None
    extras: Optional[Dict[str, Any]] = None


class LogRingBuffer:
    """
    固定大小的内存日志缓冲区

    设计原则：
    - 使用 collections.deque 实现自动淘汰
    - RLock 保证线程安全
    - 延迟初始化全局单例避免导入问题
    - 提供丰富的过滤和统计接口

    性能特征：
    - append(): O(1) (amortized)
    - get_recent(): O(n) where n = buffer size
    - get_stats(): O(1)
    """

    MAX_ENTRIES = 10000  # 默认保留 10000 条日志

    def __init__(self, max_entries: int = MAX_ENTRIES):
        """
        初始化缓冲区

        Args:
            max_entries: 最大保留条目数，超过后自动淘汰最旧的条目
        """
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
        """
        追加日志条目（线程安全）

        Args:
            entry: 结构化日志条目
        """
        with self._lock:
            self._buffer.append(entry)
            self._stats["total_appended"] += 1
            self._stats["last_timestamp"] = entry.timestamp

            # 更新级别分布统计
            level = entry.level.upper()
            self._stats["level_distribution"][level] = (
                self._stats["level_distribution"].get(level, 0) + 1
            )

            # 检查是否有条目被淘汰
            if len(self._buffer) == self.maxlen:
                self._stats["total_evicted"] += 1

    def append_from_dict(self, data: Dict[str, Any]) -> None:
        """
        从字典创建并追加日志条目（便捷方法）

        Args:
            data: 包含日志字段的字典
        """
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
        worker_id: Optional[str] = None,
    ) -> None:
        """
        追加原始日志字符串（便捷方法）

        自动解析时间戳、检测日志级别

        Args:
            message: 日志消息内容
            level: 日志级别 (DEBUG/INFO/WARNING/ERROR)
            logger_name: 日志器名称
            worker_id: 关联的 Worker ID
        """
        # 尝试从消息中提取更精确的级别
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
        level: Optional[str] = None,
        worker_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        keyword: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        查询最近的日志条目

        Args:
            limit: 最大返回数量
            level: 日志级别过滤 (DEBUG/INFO/WARNING/ERROR)
            worker_id: Worker ID 过滤
            start_time: 开始时间（包含）
            end_time: 结束时间（包含）
            keyword: 关键词搜索（消息内容匹配，不区分大小写）

        Returns:
            匹配的日志条目列表（字典格式，按时间倒序）
        """
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
                except (ValueError, TypeError):
                    pass

            if end_time:
                try:
                    entry_ts = datetime.fromisoformat(entry.timestamp)
                    if entry_ts > end_time:
                        continue
                except (ValueError, TypeError):
                    pass

            if keyword and keyword.lower() not in entry.message.lower():
                continue

            filtered.append(asdict(entry))

        return filtered[-limit:]

    def get_stats(self) -> Dict[str, Any]:
        """
        获取缓冲区统计信息

        Returns:
            包含各项统计指标的字典
        """
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
        """清空缓冲区"""
        with self._lock:
            cleared_count = len(self._buffer)
            self._buffer.clear()
            self._stats["total_evicted"] += cleared_count
            self._stats["last_timestamp"] = None

    def search(
        self,
        query: str,
        limit: int = 100,
        case_sensitive: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        全文搜索日志

        Args:
            query: 搜索关键词
            limit: 最大返回数
            case_sensitive: 是否区分大小写

        Returns:
            匹配的日志列表
        """
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

    def get_level_counts(self) -> Dict[str, int]:
        """获取各级别日志的数量统计"""
        with self._lock:
            return dict(self._stats["level_distribution"])

    def export_json(self, indent: int = 2) -> str:
        """
        导出当前所有日志为 JSON 字符串

        Args:
            indent: JSON 缩进空格数

        Returns:
            JSON 格式的日志数据
        """
        import json

        with self._lock:
            entries = [asdict(e) for e in self._buffer]

        return json.dumps({
            "exported_at": datetime.now().isoformat(),
            "total_entries": len(entries),
            "entries": entries,
        }, indent=indent, ensure_ascii=False)


# 全局单例（懒初始化）
_global_buffer: Optional[LogRingBuffer] = None
_buffer_lock = threading.Lock()


def get_global_buffer() -> LogRingBuffer:
    """
    获取全局日志缓冲区（懒初始化单例）

    Returns:
        LogRingBuffer: 全局唯一的日志缓冲区实例
    """
    global _global_buffer
    if _global_buffer is None:
        with _buffer_lock:
            if _global_buffer is None:
                _global_buffer = LogRingBuffer()
    return _global_buffer


def reset_global_buffer():
    """重置全局缓冲区（用于测试）"""
    global _global_buffer
    with _buffer_lock:
        _global_buffer = None
