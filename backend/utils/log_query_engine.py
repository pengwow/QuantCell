# -*- coding: utf-8 -*-
"""
日志查询引擎

提供高性能的日志查询功能，基于 FileLogManager 实现。
包含结果缓存、并行处理等优化机制。
"""

import time
import hashlib
import threading
from datetime import datetime
from typing import Optional, Dict, Any, List, Callable
from functools import wraps

from utils.file_log_manager import (
    FileLogManager,
    LogFilters,
    PaginatedResult,
    get_file_log_manager,
)


class QueryCache:
    """
    查询结果缓存

    使用 TTL (Time To Live) 机制自动过期，
    避免频繁重复查询相同内容。
    """

    def __init__(self, max_size: int = 100, ttl_seconds: float = 30.0):
        """
        初始化缓存

        Args:
            max_size: 最大缓存条目数
            ttl_seconds: 缓存有效期（秒）
        """
        self._cache: Dict[str, tuple] = {}
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def _generate_key(self, filters: LogFilters, page: int, page_size: int) -> str:
        """生成缓存键"""
        key_data = {
            'level': filters.level,
            'log_type': filters.log_type,
            'module': filters.module,
            'trace_id': filters.trace_id,
            'start_time': filters.start_time.isoformat() if filters.start_time else None,
            'end_time': filters.end_time.isoformat() if filters.end_time else None,
            'keyword': filters.keyword,
            'page': page,
            'page_size': page_size,
        }
        key_str = str(sorted(key_data.items()))
        return hashlib.md5(key_str.encode()).hexdigest()

    def get(self, filters: LogFilters, page: int, page_size: int) -> Optional[PaginatedResult]:
        """
        获取缓存的查询结果

        Returns:
            PaginatedResult or None: 命中返回结果，未命中返回None
        """
        key = self._generate_key(filters, page, page_size)

        with self._lock:
            if key in self._cache:
                result, timestamp = self._cache[key]

                # 检查是否过期
                if time.time() - timestamp <= self._ttl:
                    self._hits += 1
                    return result
                else:
                    # 过期删除
                    del self._cache[key]

            self._misses += 1
            return None

    def set(
        self,
        filters: LogFilters,
        page: int,
        page_size: int,
        result: PaginatedResult
    ) -> None:
        """
        缓存查询结果

        Args:
            filters: 查询过滤器
            page: 页码
            page_size: 每页大小
            result: 查询结果
        """
        key = self._generate_key(filters, page, page_size)

        with self._lock:
            # 如果缓存已满，删除最旧的条目
            if len(self._cache) >= self._max_size and key not in self._cache:
                oldest_key = min(self._cache.keys(), k=lambda k: self._cache[k][1])
                del self._cache[oldest_key]

            self._cache[key] = (result, time.time())

    def clear(self) -> None:
        """清空缓存"""
        with self._lock:
            self._cache.clear()

    def get_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计信息

        Returns:
            dict: 包含命中率等统计信息
        """
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0

        return {
            'size': len(self._cache),
            'max_size': self._max_size,
            'hits': self._hits,
            'misses': self._misses,
            'hit_rate': f'{hit_rate:.1f}%',
            'ttl_seconds': self._ttl,
        }


class LogQueryEngine:
    """
    高性能日志查询引擎

    基于 FileLogManager 提供增强的查询功能：
    - 查询结果缓存
    - 性能监控
    - 并行查询优化（未来可扩展）
    """

    _instance: Optional["LogQueryEngine"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "LogQueryEngine":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, '_initialized', False):
            return

        self._initialized = True

        # 获取文件日志管理器实例
        self.file_manager = get_file_log_manager()

        # 初始化查询缓存
        self.cache = QueryCache(max_size=100, ttl_seconds=30.0)

        # 性能统计
        self._query_stats: Dict[str, Dict[str, float]] = {}
        self._stats_lock = threading.Lock()

    def query_logs(
        self,
        level: Optional[str] = None,
        log_type: Optional[str] = None,
        module: Optional[str] = None,
        trace_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        keyword: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
        use_cache: bool = True
    ) -> PaginatedResult:
        """
        执行日志查询（带缓存）

        Args:
            level: 日志级别过滤
            log_type: 日志类型过滤
            module: 模块名称过滤
            trace_id: 跟踪ID过滤
            start_time: 开始时间
            end_time: 结束时间
            keyword: 关键词搜索
            page: 页码
            page_size: 每页数量
            use_cache: 是否使用缓存

        Returns:
            PaginatedResult: 查询结果
        """
        start_time_perf = time.perf_counter()

        # 构建过滤器
        filters = LogFilters(
            level=level,
            log_type=log_type,
            module=module,
            trace_id=trace_id,
            start_time=start_time,
            end_time=end_time,
            keyword=keyword,
        )

        # 尝试从缓存获取
        if use_cache:
            cached_result = self.cache.get(filters, page, page_size)
            if cached_result is not None:
                self._record_query_stats('query_logs_cached', time.perf_counter() - start_time_perf)
                return cached_result

        # 执行实际查询
        result = self.file_manager.query_logs(filters, page=page, page_size=page_size)

        # 存入缓存
        if use_cache:
            self.cache.set(filters, page, page_size, result)

        # 记录性能统计
        elapsed = time.perf_counter() - start_time_perf
        self._record_query_stats('query_logs', elapsed)

        return result

    def get_recent_logs(
        self,
        minutes: int = 60,
        limit: int = 100,
        level: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        获取最近的日志记录

        Args:
            minutes: 最近多少分钟
            limit: 返回数量限制
            level: 日志级别过滤

        Returns:
            List[Dict]: 日志列表
        """
        start_time_perf = time.perf_counter()

        result = self.file_manager.get_recent_logs(minutes=minutes, limit=limit, level=level)

        elapsed = time.perf_counter() - start_time_perf
        self._record_query_stats('get_recent_logs', elapsed)

        return result

    def get_logs_by_trace_id(
        self,
        trace_id: str,
        page: int = 1,
        page_size: int = 50
    ) -> PaginatedResult:
        """
        根据跟踪ID获取相关日志

        Args:
            trace_id: 跟踪ID
            page: 页码
            page_size: 每页数量

        Returns:
            PaginatedResult: 相关日志列表
        """
        start_time_perf = time.perf_counter()

        result = self.file_manager.get_logs_by_trace_id(trace_id, page=page, page_size=page_size)

        elapsed = time.perf_counter() - start_time_perf
        self._record_query_stats('get_logs_by_trace_id', elapsed)

        return result

    def get_statistics(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        获取日志统计信息

        Args:
            start_time: 开始时间
            end_time: 结束时间

        Returns:
            Dict: 统计信息
        """
        start_time_perf = time.perf_counter()

        stats = self.file_manager.get_statistics(start_time=start_time, end_time=end_time)

        elapsed = time.perf_counter() - start_time_perf
        self._record_query_stats('get_statistics', elapsed)

        return {
            'total_count': stats.total_count,
            'by_level': stats.by_level,
            'by_type': stats.by_type,
        }

    def cleanup_old_logs(self, days: int = 30) -> Dict[str, Any]:
        """
        清理旧日志文件

        Args:
            days: 保留天数

        Returns:
            Dict: 清理结果
        """
        start_time_perf = time.perf_counter()

        deleted_count = self.file_manager.cleanup_old_logs(days=days)

        elapsed = time.perf_counter() - start_time_perf
        self._record_query_stats('cleanup_old_logs', elapsed)

        return {
            'success': True,
            'deleted_count': deleted_count,
            'retention_days': days,
        }

    def get_dashboard_data(self, hours: int = 24) -> Dict[str, Any]:
        """
        获取仪表板数据

        组合多个查询结果用于前端展示。

        Args:
            hours: 统计最近多少小时

        Returns:
            Dict: 仪表板数据
        """
        start_time_perf = time.perf_counter()

        end_time = datetime.utcnow()
        start_time = end_time.replace(hour=0, minute=0, second=0, microsecond=0)
        start_time = start_time.replace(day=end_time.day - (hours // 24))

        # 获取统计数据
        stats = self.get_statistics(start_time=start_time, end_time=end_time)

        # 获取错误日志
        error_result = self.query_logs(
            level='ERROR',
            start_time=start_time,
            end_time=end_time,
            page=1,
            page_size=10,
            use_cache=False  # 仪表板数据不缓存
        )

        # 获取警告日志
        warning_result = self.query_logs(
            level='WARNING',
            start_time=start_time,
            end_time=end_time,
            page=1,
            page_size=10,
            use_cache=False
        )

        elapsed = time.perf_counter() - start_time_perf
        self._record_query_stats('get_dashboard_data', elapsed)

        return {
            'time_range': {
                'start': start_time.isoformat(),
                'end': end_time.isoformat(),
                'hours': hours,
            },
            'statistics': stats,
            'recent_errors': error_result.logs,
            'recent_warnings': warning_result.logs,
        }

    def _record_query_stats(self, operation: str, elapsed: float) -> None:
        """记录查询性能统计"""
        with self._stats_lock:
            if operation not in self._query_stats:
                self._query_stats[operation] = {
                    'count': 0,
                    'total_time': 0.0,
                    'min_time': float('inf'),
                    'max_time': 0.0,
                }

            stats = self._query_stats[operation]
            stats['count'] += 1
            stats['total_time'] += elapsed
            stats['min_time'] = min(stats['min_time'], elapsed)
            stats['max_time'] = max(stats['max_time'], elapsed)

    def get_performance_stats(self) -> Dict[str, Any]:
        """
        获取性能统计信息

        Returns:
            Dict: 包含各操作的性能数据
        """
        with self._stats_lock:
            result = {}

            for op, stats in self._query_stats.items():
                count = stats['count']
                avg_time = stats['total_time'] / count if count > 0 else 0

                result[op] = {
                    'count': count,
                    'total_time_ms': round(stats['total_time'] * 1000, 2),
                    'avg_time_ms': round(avg_time * 1000, 2),
                    'min_time_ms': round(stats['min_time'] * 1000, 2) if stats['min_time'] != float('inf') else 0,
                    'max_time_ms': round(stats['max_time'] * 1000, 2),
                }

            return {
                'operations': result,
                'cache': self.cache.get_stats(),
            }

    def clear_cache(self) -> None:
        """清空查询缓存"""
        self.cache.clear()


# 全局实例
_log_query_engine_instance: Optional[LogQueryEngine] = None
_engine_lock = threading.Lock()


def get_log_query_engine() -> LogQueryEngine:
    """
    获取日志查询引擎的全局单例

    Returns:
        LogQueryEngine: 查询引擎实例
    """
    global _log_query_engine_instance

    if _log_query_engine_instance is None:
        with _engine_lock:
            if _log_query_engine_instance is None:
                _log_query_engine_instance = LogQueryEngine()

    return _log_query_engine_instance
