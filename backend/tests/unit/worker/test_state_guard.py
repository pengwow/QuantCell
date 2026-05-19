import pytest
from worker.state_guard import StateMachineGuard, OperationResult, BatchOperationResult
from worker.worker_state import WorkerState


def test_state_machine_guard_initialization():
    """测试状态机守卫器初始化"""
    guard = StateMachineGuard()
    assert guard is not None


def test_get_machine_creates_new():
    """测试获取/创建状态机"""
    guard = StateMachineGuard()
    machine = guard.get_machine(1)
    assert machine is not None
    assert machine.current_state == WorkerState.STOPPED


def test_valid_transition():
    """测试有效状态转换"""
    guard = StateMachineGuard()
    result = guard.transition(1, WorkerState.STARTING)

    assert isinstance(result, OperationResult)
    assert result.success is True
    assert result.old_state == WorkerState.STOPPED
    assert result.new_state == WorkerState.STARTING


def test_invalid_transition():
    """测试无效状态转换"""
    guard = StateMachineGuard()
    # STOPPED -> RUNNING is invalid, should go through STARTING
    result = guard.transition(1, WorkerState.RUNNING)

    assert result.success is False
    assert result.error is None


def test_batch_transition():
    """测试批量状态转换"""
    guard = StateMachineGuard()
    # First transition to STARTING for both
    guard.transition(1, WorkerState.STARTING)
    guard.transition(2, WorkerState.STARTING)
    
    # Now try transitioning both to RUNNING
    batch_result = guard.batch_transition([1, 2], WorkerState.RUNNING, "test_batch")
    
    assert isinstance(batch_result, BatchOperationResult)
    assert len(batch_result.success_ids) == 2
    assert len(batch_result.failed_dict) == 0


def test_state_history():
    """测试状态历史记录"""
    guard = StateMachineGuard()
    guard.transition(1, WorkerState.STARTING)
    guard.transition(1, WorkerState.RUNNING)
    
    history = guard.get_state_history(1)
    assert len(history) == 2


def test_invalidate_cache():
    """测试缓存失效"""
    guard = StateMachineGuard()
    guard.get_machine(1)
    assert 1 in guard._machines
    
    guard.invalidate_cache(1)
    assert 1 not in guard._machines
