"""
Worker 优化功能单元测试

覆盖范围：
1. GracefulShutdownManager - 优雅停机管理器测试
2. LogRingBuffer - 日志环形缓冲区测试

（原 StateMachineGuard 测试随 state_guard 模块删除——状态收口已统一
到 worker_state_manager，其行为由 tests/unit/worker/test_core_service.py 覆盖）

运行方式：
    cd backend && python -m pytest tests/test_worker_optimizations.py -v
"""

import asyncio

import pytest

from worker.graceful_shutdown import (
    GracefulShutdownManager,
    ShutdownConfig,
    ShutdownPhase,
    reset_shutdown_manager,
)
from worker.log_utils import (
    LogEntry,
    LogRingBuffer,
    get_global_buffer,
    reset_global_buffer,
)

# ==================== GracefulShutdownManager 测试 ====================


class TestGracefulShutdownManager:
    """优雅停机管理器测试套件"""

    @pytest.fixture(autouse=True)
    def reset_manager(self):
        """每个测试前后重置全局管理器"""
        reset_shutdown_manager()
        yield
        reset_shutdown_manager()

    @pytest.mark.asyncio
    async def test_normal_graceful_shutdown(self):
        """正常情况下的优雅停机"""
        call_order = []

        async def mock_drain():
            call_order.append("drain")

        async def mock_stop():
            call_order.append("stop")
            await asyncio.sleep(0.01)

        async def mock_cleanup():
            call_order.append("cleanup")

        mgr = GracefulShutdownManager(
            on_drain=mock_drain,
            on_stop_services=mock_stop,
            on_cleanup=mock_cleanup,
        )

        status = await mgr.shutdown()

        assert status.is_successful is True
        assert status.timeout_occurred is False
        assert call_order == ["drain", "stop", "cleanup"]

    @pytest.mark.asyncio
    async def test_timeout_during_drain(self):
        """排空阶段超时处理"""
        # force_kill_after_timeout=False：超时只记录不自杀。
        # 该字段默认 True 会让 _force_kill() 对本进程发 SIGTERM（生产语义：
        # 停机超时→自杀让 supervisor 重启），测试进程会被直接杀掉无法断言
        config = ShutdownConfig(
            total_timeout=1.0,
            drain_timeout=0.5,
            force_kill_after_timeout=False,
        )

        async def slow_operation():
            await asyncio.sleep(10)  # 模拟阻塞操作

        mgr = GracefulShutdownManager(
            config=config,
            on_drain=slow_operation,
        )

        status = await mgr.shutdown()

        assert any("超时" in err for err in status.errors)

    @pytest.mark.asyncio
    async def test_skip_phases(self):
        """跳过特定阶段"""
        call_order = []

        async def mock_stop():
            call_order.append("stop")

        config = ShutdownConfig(skip_drain=True, skip_service_stop=True)

        mgr = GracefulShutdownManager(
            config=config,
            on_stop_services=mock_stop,
        )

        status = await mgr.shutdown()

        assert status.is_successful is True
        # 只有 cleanup 阶段会执行（stop 被跳过）

    @pytest.mark.asyncio
    async def test_status_to_dict_conversion(self):
        """状态报告应可序列化为字典"""

        async def noop():
            pass

        mgr = GracefulShutdownManager(on_drain=noop, on_cleanup=noop)
        status = await mgr.shutdown()

        status_dict = status.to_dict()

        assert "phase" in status_dict
        assert "duration_seconds" in status_dict
        assert "is_successful" in status_dict
        assert "phase_results" in status_dict

    @pytest.mark.asyncio
    async def test_error_handling_in_phase(self):
        """阶段异常不应导致整个流程崩溃"""

        async def failing_phase():
            msg = "Test error"
            raise RuntimeError(msg)

        async def successful_phase():
            pass

        mgr = GracefulShutdownManager(
            on_drain=failing_phase,
            on_cleanup=successful_phase,
        )

        status = await mgr.shutdown()

        # 应该完成（即使有错误）
        assert status.phase in [ShutdownPhase.COMPLETED, ShutdownPhase.ERROR]
        assert len(status.errors) > 0


# ==================== LogRingBuffer 测试 ====================


class TestLogRingBuffer:
    """日志环形缓冲区测试套件"""

    @pytest.fixture(autouse=True)
    def reset_buffer(self):
        """每个测试前后重置全局缓冲区"""
        reset_global_buffer()
        yield
        reset_global_buffer()

    def test_append_and_retrieve(self):
        """追加和检索日志条目"""
        buffer = LogRingBuffer(max_entries=100)

        entry = LogEntry(
            timestamp="2024-01-01T00:00:00",
            level="INFO",
            message="Test message",
            worker_id="001",
        )
        buffer.append(entry)

        logs = buffer.get_recent(limit=10)

        assert len(logs) == 1
        assert logs[0]["message"] == "Test message"
        assert logs[0]["worker_id"] == "001"

    def test_max_entries_enforcement(self):
        """超过最大容量时应自动淘汰旧条目"""
        buffer = LogRingBuffer(max_entries=5)

        for i in range(10):
            buffer.append(
                LogEntry(
                    timestamp=f"2024-01-01T00:00:{i:02d}",
                    level="INFO",
                    message=f"Message {i}",
                )
            )

        stats = buffer.get_stats()
        assert stats["current_size"] == 5
        assert stats["total_evicted"] == 5

    def test_level_filtering(self):
        """按日志级别过滤"""
        buffer = LogRingBuffer()

        buffer.append(LogEntry(timestamp="T1", level="INFO", message="Info msg"))
        buffer.append(LogEntry(timestamp="T2", level="ERROR", message="Error msg"))
        buffer.append(LogEntry(timestamp="T3", level="WARNING", message="Warning msg"))

        errors = buffer.get_recent(level="ERROR")
        assert len(errors) == 1
        assert errors[0]["level"] == "ERROR"

    def test_keyword_search(self):
        """关键词搜索"""
        buffer = LogRingBuffer()

        buffer.append(LogEntry(timestamp="T1", level="INFO", message="Order placed"))
        buffer.append(LogEntry(timestamp="T2", level="INFO", message="Connection established"))
        buffer.append(LogEntry(timestamp="T3", level="ERROR", message="Order timeout"))

        results = buffer.search(query="order")
        assert len(results) == 2

    def test_raw_message_append(self):
        """原始消息追加和自动级别检测"""
        buffer = LogRingBuffer()

        buffer.append_raw("[ERROR] Something failed")
        buffer.append_raw("Normal info message")
        buffer.append_raw("[WARN] Warning here")

        errors = buffer.get_recent(level="ERROR")
        assert len(errors) == 1
        assert "Something failed" in errors[0]["message"]

    def test_statistics_tracking(self):
        """统计信息跟踪"""
        buffer = LogRingBuffer(max_entries=50)

        buffer.append(LogEntry(level="INFO", message="msg1"))
        buffer.append(LogEntry(level="ERROR", message="msg2"))
        buffer.append(LogEntry(level="INFO", message="msg3"))

        stats = buffer.get_stats()

        assert stats["total_appended"] == 3
        assert stats["level_distribution"]["INFO"] == 2
        assert stats["level_distribution"]["ERROR"] == 1

    def test_global_singleton(self):
        """全局单例行为"""
        buf1 = get_global_buffer()
        buf2 = get_global_buffer()

        assert buf1 is buf2

    def test_clear_buffer(self):
        """清空缓冲区"""
        buffer = LogRingBuffer()

        buffer.append(LogEntry(message="msg1"))
        buffer.append(LogEntry(message="msg2"))
        assert buffer.get_stats()["current_size"] == 2

        buffer.clear()
        assert buffer.get_stats()["current_size"] == 0

    def test_export_json(self):
        """JSON导出功能"""
        buffer = LogRingBuffer()

        buffer.append(
            LogEntry(
                timestamp="2024-01-01T00:00:00",
                level="INFO",
                message="Test",
            )
        )

        json_str = buffer.export_json()

        assert "entries" in json_str
        assert "Test" in json_str


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
