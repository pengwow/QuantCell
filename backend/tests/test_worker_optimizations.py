"""
Worker 优化功能单元测试

覆盖范围：
1. StateMachineGuard - 状态机守卫器测试
2. GracefulShutdownManager - 优雅停机管理器测试
3. LogRingBuffer - 日志环形缓冲区测试

运行方式：
    cd backend && python -m pytest tests/test_worker_optimizations.py -v
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock

# 导入被测模块
from worker.state_guard import (
    StateMachineGuard,
    OperationResult,
    BatchOperationResult,
    WorkerState,
    StateMachine,
)
from worker.graceful_shutdown import (
    GracefulShutdownManager,
    ShutdownConfig,
    ShutdownStatus,
    ShutdownPhase,
    reset_shutdown_manager,
)
from worker.log_ring_buffer import (
    LogRingBuffer,
    LogEntry,
    get_global_buffer,
    reset_global_buffer,
)


# ==================== StateMachineGuard 测试 ====================

class TestStateMachineGuard:
    """状态机守卫器测试套件"""

    def setup_method(self):
        """每个测试方法前重置"""
        self.guard = StateMachineGuard()

    def test_single_valid_transition(self):
        """单个有效状态转换"""
        result = self.guard.transition(
            worker_id=1,
            target_state=WorkerState.STARTING,
        )

        assert result.success is True
        assert result.worker_id == 1
        assert result.old_state == WorkerState.STOPPED  # 默认初始状态
        assert result.new_state == WorkerState.STARTING

    def test_invalid_transition_rejected(self):
        """非法状态转换应被拒绝"""
        # 先转换到 STARTING
        self.guard.transition(1, WorkerState.STARTING)

        # 尝试再次 STARTING（应该失败）
        result = self.guard.transition(1, WorkerState.STARTING)

        assert result.success is False
        assert "非法状态转换" in result.message

    def test_batch_transition_all_success(self):
        """批量转换全部成功"""
        result = asyncio.get_event_loop().run_until_complete(
            self.guard.batch_transition(
                worker_ids=[1, 2, 3],
                target_state=WorkerState.STARTING,
            )
        )

        assert result.all_success is True
        assert len(result.success_ids) == 3
        assert len(result.failed_dict) == 0

    def test_batch_mixed_success_failure(self):
        """批量操作中部分成功、部分失败"""
        # Worker 1 先转换为 RUNNING（可以停止）
        self.guard.transition(1, WorkerState.STARTING)
        self.guard.transition(1, WorkerState.RUNNING)

        # Worker 2 保持 STOPPED（不能停止）
        result = asyncio.get_event_loop().run_until_complete(
            self.guard.batch_transition(
                worker_ids=[1, 2],
                target_state=WorkerState.STOPPING,
            )
        )

        assert result.partial_failure is True
        assert len(result.success_ids) >= 1
        assert len(result.failed_dict) >= 1

    def test_state_history_recorded(self):
        """状态转换历史应被记录"""
        self.guard.transition(1, WorkerState.STARTING)
        self.guard.transition(1, WorkerState.RUNNING)

        history = self.guard.get_state_history(worker_id=1)

        assert len(history) == 2
        assert history[0]["old_state"] == "stopped"
        assert history[0]["new_state"] == "starting"
        assert history[1]["old_state"] == "starting"
        assert history[1]["new_state"] == "running"

    def test_statistics_collection(self):
        """统计信息应正确收集"""
        self.guard.transition(1, WorkerState.STARTING)
        self.guard.transition(2, WorkerState.RUNNING)

        stats = self.guard.get_statistics()

        assert stats["cached_machines"] == 2
        assert stats["total_transitions"] == 2

    def test_cache_invalidation(self):
        """缓存失效应强制重新加载"""
        self.guard.transition(1, WorkerState.STARTING)
        assert 1 in self.guard._machines

        self.guard.invalidate_cache(worker_id=1)
        assert 1 not in self.guard._machines


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
        config = ShutdownConfig(total_timeout=1.0, drain_timeout=0.5)

        async def slow_operation():
            await asyncio.sleep(10)  # 模拟阻塞操作

        mgr = GracefulShutdownManager(
            config=config,
            on_drain=slow_operation,
        )

        status = await mgr.shutdown()

        assert status.timeout_occurred is True
        assert any("timed out" in err for err in status.errors)

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
            raise RuntimeError("Test error")

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
            buffer.append(LogEntry(
                timestamp=f"2024-01-01T00:00:{i:02d}",
                level="INFO",
                message=f"Message {i}",
            ))

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

        buffer.append(LogEntry(
            timestamp="2024-01-01T00:00:00",
            level="INFO",
            message="Test",
        ))

        json_str = buffer.export_json()

        assert "entries" in json_str
        assert "Test" in json_str


# ==================== 集成测试 ====================

class TestIntegration:
    """集成测试：验证组件协同工作"""

    @pytest.mark.asyncio
    async def test_state_machine_with_graceful_shutdown(self):
        """状态机和优雅停机的集成"""
        guard = StateMachineGuard()
        state_changed = False

        async def on_drain():
            nonlocal state_changed
            guard.transition(1, WorkerState.STOPPING)
            state_changed = True

        mgr = GracefulShutdownManager(
            config=ShutdownConfig(drain_timeout=1.0),
            on_drain=on_drain,
        )

        # 初始状态：RUNNING
        guard.transition(1, WorkerState.RUNNING)

        # 执行优雅停机
        status = await mgr.shutdown()

        assert state_changed is True
        final_state = guard.get_current_state(1)
        assert final_state == WorkerState.STOPPING

    def test_logging_during_state_transitions(self):
        """状态转换过程中的日志记录"""
        guard = StateMachineGuard()
        buffer = LogRingBuffer()

        # 模拟状态转换并记录日志
        buffer.append_raw(f"[INFO] Starting transition to STARTING")
        guard.transition(1, WorkerState.STARTING)
        buffer.append_raw(f"[SUCCESS] Transition completed: STOPPED -> STARTING")

        logs = buffer.get_recent(limit=10)

        assert any("Starting transition" in log["message"] for log in logs)
        assert any("Transition completed" in log["message"] for log in logs)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
