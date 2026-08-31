"""
Trading Worker 简化单元测试

测试 Worker 状态管理组件的单元功能，不依赖 zmq 和 binance 模块。

注意：旧版本通过 spec_from_file_location 加载模块并把 sqlalchemy/collector/
utils/worker 等顶层包替换为 Mock（sys.modules 直改且不恢复），在全量测试时
会污染全局模块缓存，导致后续集成测试出现 "collector.db is not a package"
等连锁错误。现改为直接 import 真实模块（依赖均在环境中存在）。
"""

import pytest

from worker.worker_state import WorkerState, WorkerStatus

# =============================================================================
# Worker 状态测试
# =============================================================================


class TestWorkerState:
    """Worker 状态测试"""

    def test_worker_state_transitions(self):
        """测试 Worker 状态转换"""
        status = WorkerStatus(worker_id="test-worker")

        # 初始状态是 INITIALIZING
        assert status.state == WorkerState.INITIALIZING

        # 初始化完成
        status.update_state(WorkerState.INITIALIZED)
        assert status.state == WorkerState.INITIALIZED

        # 启动
        status.update_state(WorkerState.STARTING)
        assert status.state == WorkerState.STARTING

        status.update_state(WorkerState.RUNNING)
        assert status.state == WorkerState.RUNNING

        # 暂停
        status.update_state(WorkerState.PAUSED)
        assert status.state == WorkerState.PAUSED

        # 恢复
        status.update_state(WorkerState.RUNNING)
        assert status.state == WorkerState.RUNNING

        # 停止
        status.update_state(WorkerState.STOPPING)
        assert status.state == WorkerState.STOPPING

    def test_worker_error_handling(self):
        """测试 Worker 错误处理"""
        status = WorkerStatus(worker_id="test-worker")

        # 记录错误
        status.record_error("Test error")
        assert status.errors_count == 1
        assert status.last_error == "Test error"
        assert status.last_error_time is not None

        # 记录多个错误
        status.record_error("Another error")
        assert status.errors_count == 2
        assert status.last_error == "Another error"

    def test_worker_heartbeat(self):
        """测试 Worker 心跳"""
        status = WorkerStatus(worker_id="test-worker")

        # 先转换到 RUNNING 状态（is_healthy 要求 RUNNING 或 PAUSED 状态）
        status.update_state(WorkerState.INITIALIZED)
        status.update_state(WorkerState.STARTING)
        status.update_state(WorkerState.RUNNING)

        # 更新心跳
        status.update_heartbeat()
        assert status.last_heartbeat is not None

        # 检查健康状态
        assert status.is_healthy() is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
