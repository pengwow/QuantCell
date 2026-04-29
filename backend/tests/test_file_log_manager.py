# -*- coding: utf-8 -*-
"""
文件日志管理器单元测试

测试基于文件的日志系统的核心功能，包括：
- 日志写入和读取
- 多条件过滤查询
- 分页功能
- 统计计算
- 旧日志清理
"""

import pytest
import sys
import os
import json
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timedelta

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.logger import LogRecord, LogLevel, LogType
from utils.file_log_manager import (
    FileLogManager,
    LogFilters,
    PaginatedResult,
    LogStatistics,
    get_file_log_manager,
    shutdown_file_log_manager,
)


@pytest.fixture(scope="function")
def temp_log_dir():
    """
    创建临时日志目录的fixture

    每个测试函数使用独立的临时目录，避免测试间干扰。
    """
    temp_dir = tempfile.mkdtemp(prefix="test_logs_")
    yield temp_dir
    # 测试结束后清理临时目录
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture(scope="function")
def file_manager(temp_log_dir):
    """
    创建使用临时目录的FileLogManager实例

    使用新的实例而非全局单例，确保测试隔离性。
    """
    manager = FileLogManager(base_log_dir=temp_log_dir)
    yield manager
    manager.close()


class TestFileLogManagerInit:
    """测试 FileLogManager 初始化"""

    def test_init_creates_directory(self, temp_log_dir):
        """测试初始化时创建日志目录"""
        log_dir = Path(temp_log_dir) / "system"
        assert not log_dir.exists()

        manager = FileLogManager(base_log_dir=temp_log_dir)

        assert log_dir.exists()
        assert log_dir.is_dir()
        manager.close()

    def test_singleton_pattern(self):
        """测试单例模式"""
        manager1 = FileLogManager()
        manager2 = FileLogManager()

        assert manager1 is manager2


class TestLogWriting:
    """测试日志写入功能"""

    def test_write_single_log(self, file_manager):
        """测试写入单条日志"""
        record = LogRecord(
            timestamp=datetime.utcnow(),
            level=LogLevel.INFO.value,
            message="测试日志消息",
            module="test_module",
            function="test_function",
            line=42,
            logger_name="test_logger",
            log_type=LogType.APPLICATION.value,
            trace_id="test-trace-123",
        )

        result = file_manager.write_log(record)
        assert result is True

    def test_write_batch_logs(self, file_manager):
        """测试批量写入日志"""
        records = []
        for i in range(10):
            record = LogRecord(
                timestamp=datetime.utcnow(),
                level=LogLevel.INFO.value,
                message=f"批量测试消息 {i}",
                module="test_module",
                function="test_function",
                line=i,
                logger_name="test_logger",
                log_type=LogType.APPLICATION.value,
            )
            records.append(record)

        success_count = file_manager.write_batch(records)
        assert success_count == 10

    def test_write_different_log_types(self, file_manager):
        """测试写入不同类型的日志"""
        types = [LogType.SYSTEM, LogType.API, LogType.STRATEGY]

        for log_type in types:
            record = LogRecord(
                timestamp=datetime.utcnow(),
                level=LogLevel.INFO.value,
                message=f"{log_type.value} 类型日志",
                module="test_module",
                function="test_function",
                line=1,
                logger_name="test_logger",
                log_type=log_type.value,
            )
            result = file_manager.write_log(record)
            assert result is True

    def test_write_log_with_exception(self, file_manager):
        """测试带异常信息的日志"""
        exception_info = "Traceback (most recent call last):\n  File 'test.py', line 1, in <module>\nraise ValueError('test error')"

        record = LogRecord(
            timestamp=datetime.utcnow(),
            level=LogLevel.ERROR.value,
            message="发生错误",
            module="test_module",
            function="error_function",
            line=100,
            logger_name="test_logger",
            log_type=LogType.EXCEPTION.value,
            exception_info=exception_info,
        )

        result = file_manager.write_log(record)
        assert result is True


class TestLogQuerying:
    """测试日志查询功能"""

    def _setup_test_data(self, file_manager, count=50):
        """辅助方法：创建测试数据"""
        records = []
        for i in range(count):
            level = [LogLevel.DEBUG, LogLevel.INFO, LogLevel.WARNING, LogLevel.ERROR][i % 4]
            log_type = [LogType.SYSTEM, LogType.APPLICATION, LogType.API][i % 3]

            record = LogRecord(
                timestamp=datetime.utcnow() - timedelta(minutes=i),
                level=level.value,
                message=f"测试消息 {i}: {''.join(['word'] * (i % 5 + 1))}",
                module=f"module_{i % 3}",
                function=f"func_{i % 2}",
                line=i,
                logger_name=f"logger_{i % 2}",
                log_type=log_type.value,
                trace_id=f"trace-{i % 5}" if i % 5 == 0 else None,
            )
            records.append(record)
            file_manager.write_log(record)

        return records

    def test_query_all_logs(self, file_manager):
        """测试查询所有日志"""
        self._setup_test_data(file_manager, 20)

        filters = LogFilters()
        result = file_manager.query_logs(filters, page=1, page_size=100)

        assert isinstance(result, PaginatedResult)
        assert len(result.logs) == 20
        assert result.pagination['total'] == 20

    def test_query_with_level_filter(self, file_manager):
        """测试按级别过滤查询"""
        self._setup_test_data(file_manager, 40)

        filters = LogFilters(level='ERROR')
        result = file_manager.query_logs(filters, page=1, page_size=100)

        assert all(log['level'] == 'ERROR' for log in result.logs)

    def test_query_with_type_filter(self, file_manager):
        """测试按类型过滤查询"""
        self._setup_test_data(file_manager, 30)

        filters = LogFilters(log_type='api')
        result = file_manager.query_logs(filters, page=1, page_size=100)

        assert all(log['log_type'] == 'api' for log in result.logs)

    def test_query_with_keyword_filter(self, file_manager):
        """测试关键词搜索"""
        self._setup_test_data(file_manager, 25)

        filters = LogFilters(keyword='word word')
        result = file_manager.query_logs(filters, page=1, page_size=100)

        for log in result.logs:
            assert 'word word' in log['message'].lower()

    def test_query_with_trace_id(self, file_manager):
        """测试按跟踪ID查询"""
        self._setup_test_data(file_manager, 30)

        filters = LogFilters(trace_id='trace-0')
        result = file_manager.query_logs(filters, page=1, page_size=100)

        assert all(log.get('trace_id') == 'trace-0' for log in result.logs)

    def test_pagination(self, file_manager):
        """测试分页功能"""
        self._setup_test_data(file_manager, 25)

        # 第一页
        result1 = file_manager.query_logs(LogFilters(), page=1, page_size=10)
        assert len(result1.logs) == 10
        assert result1.pagination['page'] == 1

        # 第二页
        result2 = file_manager.query_logs(LogFilters(), page=2, page_size=10)
        assert len(result2.logs) == 10
        assert result2.pagination['page'] == 2

        # 第三页（剩余5条）
        result3 = file_manager.query_logs(LogFilters(), page=3, page_size=10)
        assert len(result3.logs) == 5

    def test_time_range_filter(self, file_manager):
        """测试时间范围过滤"""
        self._setup_test_data(file_manager, 20)

        now = datetime.utcnow()
        start_time = now - timedelta(minutes=10)
        end_time = now - timedelta(minutes=5)

        filters = LogFilters(start_time=start_time, end_time=end_time)
        result = file_manager.query_logs(filters, page=1, page_size=100)

        for log in result.logs:
            log_time = datetime.fromisoformat(log['timestamp'])
            assert start_time <= log_time <= end_time


class TestStatistics:
    """测试统计功能"""

    def test_get_statistics(self, file_manager):
        """测试获取统计信息"""
        # 写入不同级别的日志
        levels = [LogLevel.INFO] * 10 + [LogLevel.ERROR] * 5 + [LogLevel.WARNING] * 3
        for i, level in enumerate(levels):
            record = LogRecord(
                timestamp=datetime.utcnow(),
                level=level.value,
                message=f"统计测试 {i}",
                module="stat_module",
                function="stat_func",
                line=i,
                logger_name="stat_logger",
                log_type=LogType.APPLICATION.value,
            )
            file_manager.write_log(record)

        stats = file_manager.get_statistics()

        assert isinstance(stats, LogStatistics)
        assert stats.total_count == 18
        assert stats.by_level.get('INFO', 0) == 10
        assert stats.by_level.get('ERROR', 0) == 5
        assert stats.by_level.get('WARNING', 0) == 3


class TestRecentLogs:
    """测试最近日志功能"""

    def test_get_recent_logs(self, file_manager):
        """测试获取最近日志"""
        # 写入一些历史日志
        for i in range(10):
            record = LogRecord(
                timestamp=datetime.utcnow() - timedelta(minutes=i * 10),
                level=LogLevel.INFO.value,
                message=f"最近日志 {i}",
                module="recent_module",
                function="recent_func",
                line=i,
                logger_name="recent_logger",
                log_type=LogType.APPLICATION.value,
            )
            file_manager.write_log(record)

        recent_logs = file_manager.get_recent_logs(minutes=60, limit=5)

        assert len(recent_logs) <= 5
        # 应该是时间倒序（最新的在前）
        if len(recent_logs) > 1:
            time1 = datetime.fromisoformat(recent_logs[0]['timestamp'])
            time2 = datetime.fromisoformat(recent_logs[1]['timestamp'])
            assert time1 >= time2

    def test_get_recent_logs_with_level_filter(self, file_manager):
        """测试带级别过滤的最近日志"""
        for i, level in enumerate([LogLevel.INFO, LogLevel.ERROR, LogLevel.WARNING]):
            record = LogRecord(
                timestamp=datetime.utcnow() - timedelta(minutes=i),
                level=level.value,
                message=f"过滤测试 {i}",
                module="filter_module",
                function="filter_func",
                line=i,
                logger_name="filter_logger",
                log_type=LogType.APPLICATION.value,
            )
            file_manager.write_log(record)

        error_logs = file_manager.get_recent_logs(minutes=60, limit=10, level='ERROR')

        assert all(log['level'] == 'ERROR' for log in error_logs)


class TestCleanup:
    """测试旧日志清理功能"""

    def test_cleanup_old_logs(self, file_manager, temp_log_dir):
        """测试清理旧日志"""
        # 创建不同日期的日志（通过修改文件名模拟）
        base_path = Path(temp_log_dir) / "system" / "application"
        base_path.mkdir(parents=True, exist_ok=True)

        # 创建一个"旧"日志文件（30天前）
        old_date = datetime.utcnow() - timedelta(days=35)
        old_file = base_path / f"application_{old_date.strftime('%Y%m%d')}.log"
        old_file.write_text("old log entry\n")

        # 创建一个"新"日志文件（昨天）
        yesterday = datetime.utcnow() - timedelta(days=1)
        new_file = base_path / f"application_{yesterday.strftime('%Y%m%d')}.log"
        new_file.write_text("new log entry\n")

        # 执行清理（保留30天）
        deleted_count = file_manager.cleanup_old_logs(days=30)

        assert deleted_count == 1
        assert not old_file.exists()
        assert new_file.exists()


class TestLogQueryEngine:
    """测试日志查询引擎（高级功能）"""

    def _setup_engine_with_data(self, tmp_path):
        """辅助方法：创建带数据的查询引擎"""
        from utils.log_query_engine import LogQueryEngine

        # 重置全局实例以使用临时目录
        import utils.file_log_manager as flm
        original_instance = flm._file_log_manager_instance
        flm._file_log_manager_instance = None

        manager = FileLogManager(base_log_dir=str(tmp_path))

        # 写入测试数据
        for i in range(20):
            record = LogRecord(
                timestamp=datetime.utcnow() - timedelta(minutes=i),
                level=[LogLevel.INFO, LogLevel.ERROR][i % 2],
                message=f"引擎测试消息 {i}",
                module="engine_module",
                function="engine_func",
                line=i,
                logger_name="engine_logger",
                log_type=LogType.APPLICATION.value,
            )
            manager.write_log(record)

        engine = LogQueryEngine()
        engine.file_manager = manager

        return engine, lambda: setattr(flm, '_file_log_manager_instance', original_instance)

    def test_query_with_cache(self, temp_log_dir):
        """测试带缓存的查询"""
        import utils.log_query_engine as lqe
        original_instance = lqe._log_query_engine_instance
        lqe._log_query_engine_instance = None

        try:
            engine, cleanup = self._setup_engine_with_data(temp_log_dir)

            # 第一次查询（无缓存）
            result1 = engine.query_logs(page=1, page_size=10, use_cache=True)
            assert len(result1.logs) > 0

            # 第二次查询（应该命中缓存）
            result2 = engine.query_logs(page=1, page_size=10, use_cache=True)
            assert len(result2.logs) == len(result1.logs)

            # 验证缓存统计
            cache_stats = engine.cache.get_stats()
            assert cache_stats['hits'] >= 1

            cleanup()
        finally:
            lqe._log_query_engine_instance = original_instance

    def test_performance_stats(self, temp_log_dir):
        """测试性能统计"""
        import utils.log_query_engine as lqe
        original_instance = lqe._log_query_engine_instance
        lqe._log_query_engine_instance = None

        try:
            engine, cleanup = self._setup_engine_with_data(temp_log_dir)

            # 执行几次查询
            engine.query_logs(level='INFO')
            engine.get_statistics()
            engine.get_recent_logs(minutes=60)

            # 获取性能统计
            perf_stats = engine.get_performance_stats()

            assert 'operations' in perf_stats
            assert 'cache' in perf_stats
            assert 'query_logs' in perf_stats['operations']
            assert 'get_statistics' in perf_stats['operations']

            cleanup()
        finally:
            lqe._log_query_engine_instance = original_instance


class TestEdgeCases:
    """测试边界情况"""

    def test_empty_query_result(self, file_manager):
        """测试空结果查询"""
        filters = LogFilters(level='NONEXISTENT_LEVEL')
        result = file_manager.query_logs(filters)

        assert len(result.logs) == 0
        assert result.pagination['total'] == 0

    def test_special_characters_in_message(self, file_manager):
        """测试消息中的特殊字符"""
        special_messages = [
            "包含中文的消息",
            "Message with émojis 🎉🚀",
            "JSON-like {\"key\": \"value\"}",
            "Multi\nLine\nMessage",
            "Tabs\there\tand\tthere",
            "Quotes: 'single' and \"double\"",
        ]

        for msg in special_messages:
            record = LogRecord(
                timestamp=datetime.utcnow(),
                level=LogLevel.INFO,
                message=msg,
                module="special_module",
                function="special_func",
                line=1,
                logger_name="special_logger",
                log_type=LogType.APPLICATION,
            )
            file_manager.write_log(record)

        # 查询并验证特殊字符保留
        result = file_manager.query_logs(LogFilters(module='special_module'))
        messages = [log['message'] for log in result.logs]

        for msg in special_messages:
            assert msg in messages

    def test_very_long_message(self, file_manager):
        """测试超长消息截断"""
        long_message = "x" * 10000

        record = LogRecord(
            timestamp=datetime.utcnow(),
            level=LogLevel.INFO,
            message=long_message,
            module="long_module",
            function="long_func",
            line=1,
            logger_name="long_logger",
            log_type=LogType.APPLICATION,
        )

        result = file_manager.write_log(record)
        assert result is True

        # 验证可以读取回完整消息
        logs = file_manager.query_logs(LogFilters(module='long_module'))
        assert len(logs.logs) == 1
        assert len(logs.logs[0]['message']) == 10000


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
