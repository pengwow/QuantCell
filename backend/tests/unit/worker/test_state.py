"""
Worker 状态机模块单元测试

测试 WorkerState、WorkerStatus 和 StateMachine 的功能
"""

import pytest
from datetime import datetime, timedelta
from worker.state import WorkerState, WorkerStatus, StateMachine


class TestWorkerState:
    """测试 WorkerState 枚举"""

    def test_state_values(self):
        """测试状态值是否正确"""
        assert WorkerState.INITIALIZING.value == "initializing"
        assert WorkerState.RUNNING.value == "running"
        assert WorkerState.STOPPED.value == "stopped"
        assert WorkerState.ERROR.value == "error"

    def test_is_active(self):
        """测试 is_active 方法"""
        assert WorkerState.RUNNING.is_active() is True
        assert WorkerState.PAUSED.is_active() is True
        assert WorkerState.INITIALIZING.is_active() is False
        assert WorkerState.STOPPED.is_active() is False
        assert WorkerState.ERROR.is_active() is False

    def test_is_terminal(self):
        """测试 is_terminal 方法"""
        assert WorkerState.STOPPED.is_terminal() is True
        assert WorkerState.ERROR.is_terminal() is True
        assert WorkerState.RUNNING.is_terminal() is False
        assert WorkerState.INITIALIZING.is_terminal() is False

    def test_valid_transitions(self):
        """测试合法的状态转换"""
        # INITIALIZING -> INITIALIZED
        assert WorkerState.INITIALIZING.can_transition_to(WorkerState.INITIALIZED) is True
        # INITIALIZED -> STARTING
        assert WorkerState.INITIALIZED.can_transition_to(WorkerState.STARTING) is True
        # STARTING -> RUNNING
        assert WorkerState.STARTING.can_transition_to(WorkerState.RUNNING) is True
        # RUNNING -> PAUSED
        assert WorkerState.RUNNING.can_transition_to(WorkerState.PAUSED) is True
        # RUNNING -> STOPPING
        assert WorkerState.RUNNING.can_transition_to(WorkerState.STOPPING) is True
        # PAUSED -> RUNNING
        assert WorkerState.PAUSED.can_transition_to(WorkerState.RUNNING) is True
        # STOPPING -> STOPPED
        assert WorkerState.STOPPING.can_transition_to(WorkerState.STOPPED) is True

    def test_invalid_transitions(self):
        """测试非法的状态转换"""
        # 不能从 RUNNING 直接回到 INITIALIZING
        assert WorkerState.RUNNING.can_transition_to(WorkerState.INITIALIZING) is False
        # 不能从 STOPPED 直接到 RUNNING
        assert WorkerState.STOPPED.can_transition_to(WorkerState.RUNNING) is False
        # 不能从 ERROR 直接到 RUNNING
        assert WorkerState.ERROR.can_transition_to(WorkerState.RUNNING) is False


class TestWorkerStatus:
    """测试 WorkerStatus 类"""

    @pytest.fixture
    def worker_status(self):
        """创建测试用的 WorkerStatus 实例"""
        return WorkerStatus(
            worker_id="test-worker-001",
            strategy_path="/path/to/strategy.py",
            symbols=["BTC/USDT", "ETH/USDT"]
        )

    def test_initial_state(self, worker_status):
        """测试初始状态"""
        assert worker_status.worker_id == "test-worker-001"
        assert worker_status.state == WorkerState.INITIALIZING
        assert worker_status.strategy_path == "/path/to/strategy.py"
        assert worker_status.symbols == ["BTC/USDT", "ETH/USDT"]
        assert worker_status.pid is None
        assert worker_status.errors_count == 0

    def test_update_state_success(self, worker_status):
        """测试成功的状态更新"""
        # 按照正确的路径更新状态
        assert worker_status.update_state(WorkerState.INITIALIZED) is True
        assert worker_status.state == WorkerState.INITIALIZED
        
        assert worker_status.update_state(WorkerState.STARTING) is True
        assert worker_status.state == WorkerState.STARTING
        
        assert worker_status.update_state(WorkerState.RUNNING) is True
        assert worker_status.state == WorkerState.RUNNING
        assert worker_status.started_at is not None

    def test_update_state_failure(self, worker_status):
        """测试失败的状态更新"""
        # 直接从 INITIALIZING 到 RUNNING 应该失败
        assert worker_status.update_state(WorkerState.RUNNING) is False
        assert worker_status.state == WorkerState.INITIALIZING

    def test_update_heartbeat(self, worker_status):
        """测试心跳更新"""
        assert worker_status.last_heartbeat is None
        
        worker_status.update_heartbeat()
        assert worker_status.last_heartbeat is not None
        
        # 再次更新
        old_heartbeat = worker_status.last_heartbeat
        worker_status.update_heartbeat()
        assert worker_status.last_heartbeat >= old_heartbeat

    def test_record_error(self, worker_status):
        """测试错误记录"""
        assert worker_status.errors_count == 0
        assert worker_status.last_error is None
        
        worker_status.record_error("Test error message")
        
        assert worker_status.errors_count == 1
        assert worker_status.last_error == "Test error message"
        assert worker_status.last_error_time is not None
        
        # 记录第二个错误
        worker_status.record_error("Another error")
        assert worker_status.errors_count == 2
        assert worker_status.last_error == "Another error"

    def test_is_healthy(self, worker_status):
        """测试健康检查"""
        # 初始状态不健康（没有心跳）
        assert worker_status.is_healthy() is False
        
        # 更新到运行状态并设置心跳
        worker_status.update_state(WorkerState.INITIALIZED)
        worker_status.update_state(WorkerState.STARTING)
        worker_status.update_state(WorkerState.RUNNING)
        worker_status.update_heartbeat()
        
        assert worker_status.is_healthy() is True
        
        # 模拟心跳超时
        worker_status.last_heartbeat = datetime.now() - timedelta(seconds=60)
        assert worker_status.is_healthy(heartbeat_timeout=30) is False

    def test_is_healthy_not_running(self, worker_status):
        """测试非运行状态下的健康检查"""
        worker_status.update_heartbeat()
        # 初始状态不是 RUNNING，应该不健康
        assert worker_status.is_healthy() is False

    def test_to_dict(self, worker_status):
        """测试转换为字典"""
        worker_status.update_state(WorkerState.INITIALIZED)
        worker_status.update_state(WorkerState.STARTING)
        worker_status.update_state(WorkerState.RUNNING)
        worker_status.update_heartbeat()
        worker_status.record_error("Test error")
        
        data = worker_status.to_dict()
        
        assert data["worker_id"] == "test-worker-001"
        assert data["state"] == "running"
        assert data["strategy_path"] == "/path/to/strategy.py"
        assert data["symbols"] == ["BTC/USDT", "ETH/USDT"]
        assert "created_at" in data
        assert "started_at" in data
        assert "last_heartbeat" in data
        assert data["errors_count"] == 1
        assert data["last_error"] == "Test error"


class TestStateMachine:
    """测试 StateMachine 类"""

    @pytest.fixture
    def state_machine(self):
        """创建测试用的 StateMachine 实例"""
        return StateMachine(WorkerState.INITIALIZING)

    def test_initial_state(self, state_machine):
        """测试初始状态"""
        assert state_machine.current_state == WorkerState.INITIALIZING

    def test_transition_to_success(self, state_machine):
        """测试成功的状态转换"""
        assert state_machine.transition_to(WorkerState.INITIALIZED) is True
        assert state_machine.current_state == WorkerState.INITIALIZED
        
        assert state_machine.transition_to(WorkerState.STARTING) is True
        assert state_machine.current_state == WorkerState.STARTING

    def test_transition_to_failure(self, state_machine):
        """测试失败的状态转换"""
        assert state_machine.transition_to(WorkerState.RUNNING) is False
        assert state_machine.current_state == WorkerState.INITIALIZING

    def test_get_state_history(self, state_machine):
        """测试获取状态历史"""
        history = state_machine.get_state_history()
        assert len(history) == 1
        assert history[0][0] == WorkerState.INITIALIZING
        
        # 进行状态转换
        state_machine.transition_to(WorkerState.INITIALIZED)
        state_machine.transition_to(WorkerState.STARTING)
        
        history = state_machine.get_state_history()
        assert len(history) == 3
        assert history[0][0] == WorkerState.INITIALIZING
        assert history[1][0] == WorkerState.INITIALIZED
        assert history[2][0] == WorkerState.STARTING

    def test_can_transition_to(self, state_machine):
        """测试状态转换检查"""
        assert state_machine.can_transition_to(WorkerState.INITIALIZED) is True
        assert state_machine.can_transition_to(WorkerState.RUNNING) is False

    def test_transition_handler(self, state_machine):
        """测试状态转换处理器"""
        handler_called = []
        
        def handler(old_state, new_state):
            handler_called.append((old_state, new_state))
        
        state_machine.register_transition_handler(WorkerState.INITIALIZED, handler)
        
        state_machine.transition_to(WorkerState.INITIALIZED)
        
        assert len(handler_called) == 1
        assert handler_called[0] == (WorkerState.INITIALIZING, WorkerState.INITIALIZED)

    def test_multiple_handlers(self, state_machine):
        """测试多个状态转换处理器"""
        calls = []
        
        def handler1(old_state, new_state):
            calls.append("handler1")
        
        def handler2(old_state, new_state):
            calls.append("handler2")
        
        state_machine.register_transition_handler(WorkerState.INITIALIZED, handler1)
        state_machine.register_transition_handler(WorkerState.INITIALIZED, handler2)
        
        state_machine.transition_to(WorkerState.INITIALIZED)
        
        assert "handler1" in calls
        assert "handler2" in calls

    def test_handler_exception_not_propagated(self, state_machine):
        """测试处理器异常不影响状态转换"""
        def bad_handler(old_state, new_state):
            raise Exception("Handler error")
        
        state_machine.register_transition_handler(WorkerState.INITIALIZED, bad_handler)
        
        # 状态转换应该成功，即使处理器抛出异常
        assert state_machine.transition_to(WorkerState.INITIALIZED) is True
        assert state_machine.current_state == WorkerState.INITIALIZED
