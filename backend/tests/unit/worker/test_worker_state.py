import pytest
from worker.worker_state import (
    WorkerState,
    StateMachine,
    WorkerStatus,
    WorkerStateRecord,
    is_valid_transition,
    WorkerStateManager,
    worker_state_manager,
)


def test_worker_state_enum():
    """测试 WorkerState 枚举"""
    assert WorkerState.STOPPED.value == "stopped"
    assert WorkerState.STARTING.value == "starting"
    assert WorkerState.RUNNING.value == "running"


def test_worker_state_is_active():
    """测试 is_active()"""
    assert WorkerState.RUNNING.is_active() is True
    assert WorkerState.PAUSED.is_active() is True
    assert WorkerState.STOPPED.is_active() is False


def test_worker_state_is_terminal():
    """测试 is_terminal()"""
    assert WorkerState.STOPPED.is_terminal() is True
    assert WorkerState.ERROR.is_terminal() is True
    assert WorkerState.RUNNING.is_terminal() is False


def test_worker_state_can_transition():
    """测试状态转换验证"""
    assert WorkerState.STOPPED.can_transition_to(WorkerState.STARTING) is True
    assert WorkerState.STOPPED.can_transition_to(WorkerState.RUNNING) is False
    assert WorkerState.STARTING.can_transition_to(WorkerState.RUNNING) is True


def test_state_machine():
    """测试状态机基本功能"""
    sm = StateMachine(WorkerState.STOPPED)
    assert sm.current_state == WorkerState.STOPPED
    
    assert sm.can_transition_to(WorkerState.STARTING) is True
    assert sm.transition_to(WorkerState.STARTING) is True
    assert sm.current_state == WorkerState.STARTING
    
    history = sm.get_state_history()
    assert len(history) == 2


def test_worker_status():
    """测试 WorkerStatus 数据类"""
    ws = WorkerStatus(worker_id="test_123")
    assert ws.worker_id == "test_123"
    assert ws.state == WorkerState.INITIALIZING
    
    assert ws.update_state(WorkerState.INITIALIZED) is True
    assert ws.state == WorkerState.INITIALIZED


def test_worker_status_to_dict():
    """测试 WorkerStatus 转字典"""
    ws = WorkerStatus(worker_id="test_123")
    d = ws.to_dict()
    assert "worker_id" in d
    assert d["worker_id"] == "test_123"


def test_is_valid_transition():
    """测试 is_valid_transition 函数"""
    assert is_valid_transition("stopped", "starting") is True
    assert is_valid_transition("stopped", "running") is False
    assert is_valid_transition("starting", "running") is True


@pytest.mark.asyncio
async def test_worker_state_manager():
    """测试 WorkerStateManager 基本功能"""
    manager = WorkerStateManager()
    # Initialize state
    assert manager is not None
    
    # Test that we can transition from stopped to starting, but first need to initialize stopped
    # Note: WorkerStateManager requires state first transition to stopped
    # Let's test the basic methods
    manager._state_cache[123] = WorkerStateRecord(worker_id=123, status="stopped")
    state = await manager.get_state(123)
    assert state is not None
    assert state.status == "stopped"
    
    success = await manager.transition(123, "starting")
    assert success is True
    
    state = await manager.get_state(123)
    assert state.status == "starting"


def test_worker_state_record_to_dict():
    """测试 WorkerStateRecord 转字典"""
    record = WorkerStateRecord(worker_id=123)
    d = record.to_dict()
    assert "worker_id" in d
    assert d["worker_id"] == 123
