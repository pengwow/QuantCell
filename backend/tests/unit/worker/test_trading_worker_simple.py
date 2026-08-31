"""
Trading Worker 简化单元测试

测试 Trading Worker 相关组件的单元功能，不依赖 zmq 和 binance 模块
"""

import os
import sys
from unittest.mock import Mock

import pytest

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../.."))


# =============================================================================
# Worker 状态测试
# =============================================================================


class TestWorkerState:
    """Worker 状态测试"""

    def test_worker_state_transitions(self):
        """测试 Worker 状态转换"""
        import importlib.util

        state_path = os.path.join(os.path.dirname(__file__), "../../../worker/worker_state.py")
        spec = importlib.util.spec_from_file_location("worker.worker_state", state_path)
        state_module = importlib.util.module_from_spec(spec)
        state_module.__package__ = "worker"

        # Mock 依赖
        sys.modules["sqlalchemy"] = Mock()
        sys.modules["sqlalchemy.orm"] = Mock()
        sys.modules["collector"] = Mock()
        sys.modules["collector.db"] = Mock()
        sys.modules["collector.db.database"] = Mock()
        sys.modules["utils"] = Mock()
        sys.modules["utils.logger"] = Mock()
        sys.modules["worker"] = Mock()
        sys.modules["worker.crud"] = Mock()

        spec.loader.exec_module(state_module)

        WorkerState = state_module.WorkerState
        WorkerStatus = state_module.WorkerStatus

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
        import importlib.util

        state_path = os.path.join(os.path.dirname(__file__), "../../../worker/worker_state.py")
        spec = importlib.util.spec_from_file_location("worker.worker_state", state_path)
        state_module = importlib.util.module_from_spec(spec)
        state_module.__package__ = "worker"

        # Mock 依赖
        sys.modules["sqlalchemy"] = Mock()
        sys.modules["sqlalchemy.orm"] = Mock()
        sys.modules["collector"] = Mock()
        sys.modules["collector.db"] = Mock()
        sys.modules["collector.db.database"] = Mock()
        sys.modules["utils"] = Mock()
        sys.modules["utils.logger"] = Mock()
        sys.modules["worker"] = Mock()
        sys.modules["worker.crud"] = Mock()

        spec.loader.exec_module(state_module)

        WorkerStatus = state_module.WorkerStatus

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
        import importlib.util

        state_path = os.path.join(os.path.dirname(__file__), "../../../worker/worker_state.py")
        spec = importlib.util.spec_from_file_location("worker.worker_state", state_path)
        state_module = importlib.util.module_from_spec(spec)
        state_module.__package__ = "worker"

        # Mock 依赖
        sys.modules["sqlalchemy"] = Mock()
        sys.modules["sqlalchemy.orm"] = Mock()
        sys.modules["collector"] = Mock()
        sys.modules["collector.db"] = Mock()
        sys.modules["collector.db.database"] = Mock()
        sys.modules["utils"] = Mock()
        sys.modules["utils.logger"] = Mock()
        sys.modules["worker"] = Mock()
        sys.modules["worker.crud"] = Mock()

        spec.loader.exec_module(state_module)

        WorkerStatus = state_module.WorkerStatus
        WorkerState = state_module.WorkerState

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
