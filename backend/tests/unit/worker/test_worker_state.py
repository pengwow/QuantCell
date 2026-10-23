import pytest

from worker.worker_state import (
    StateMachine,
    WorkerState,
    WorkerStateManager,
    WorkerStateRecord,
    WorkerStatus,
    is_valid_transition,
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


# ==================== DB 惰性水合回归测试 ====================
# 场景：新建 Worker 只写 DB 不入内存缓存，此前启动时 transition 缓存 miss
# 直接返回 False，导致 HTTP 400 "当前状态 (unknown) 不允许启动"。


class _FakeWorker:
    """monkeypatch crud.get_worker 用的最小替身，仅提供水合所需字段"""

    def __init__(self, status: str = "stopped", worker_id: int = 999):
        self.id = worker_id
        self.status = status
        self.pid = None
        self.started_at = None
        self.stopped_at = None
        self.updated_at = None


@pytest.fixture
def state_manager():
    manager = WorkerStateManager()
    manager._state_cache.clear()  # 单例实例，测试间清缓存互不污染
    return manager


@pytest.fixture
def fake_db(monkeypatch):
    """让状态管理器的 DB 访问脱离真实数据库（session/get_worker/update 均替换）"""
    from contextlib import contextmanager

    from worker import worker_state as ws_mod

    @contextmanager
    def _fake_session():
        yield None

    monkeypatch.setattr(ws_mod, "get_db_session", _fake_session)
    monkeypatch.setattr(ws_mod.crud, "update_worker_status", lambda *a, **k: None)
    return ws_mod


@pytest.mark.asyncio
async def test_transition_hydrates_new_worker_from_db(state_manager, fake_db, monkeypatch):
    """回归：新建 Worker 不在缓存时，启动应从 DB 水合后成功转换"""
    monkeypatch.setattr(fake_db.crud, "get_worker", lambda db, wid: _FakeWorker("stopped"))

    success = await state_manager.transition(999, "starting")
    assert success is True

    state = await state_manager.get_state(999)
    assert state is not None
    assert state.status == "starting"


@pytest.mark.asyncio
async def test_transition_rejects_worker_missing_everywhere(state_manager, fake_db, monkeypatch):
    """DB 中也不存在才是真的不存在，转换应拒绝"""
    monkeypatch.setattr(fake_db.crud, "get_worker", lambda db, wid: None)

    assert await state_manager.transition(424242, "starting") is False


@pytest.mark.asyncio
async def test_get_state_hydrates_residue_as_stopped(state_manager, fake_db, monkeypatch):
    """DB 残留中间状态（如 starting）水合时按 stopped 处理，随后可正常启动"""
    monkeypatch.setattr(fake_db.crud, "get_worker", lambda db, wid: _FakeWorker("starting"))

    state = await state_manager.get_state(999)
    assert state is not None
    assert state.status == "stopped"

    assert await state_manager.transition(999, "starting") is True


# ==================== 陈旧中间态自愈回归测试 ====================
# 场景：同步收尾路径（stop/start 内部）直写 DB 不动内存缓存，缓存停在
# stopping 而 DB 已是 stopped；缓存命中后不再水合 → Worker 永久卡死。


@pytest.mark.asyncio
async def test_transition_self_heals_stale_stopping_cache(state_manager, fake_db, monkeypatch):
    """回归：缓存 stopping 超龄且 DB 已 stopped → 以 DB 为准自愈，start 放行"""
    from datetime import datetime, timedelta

    from worker.worker_state import STALE_INTERMEDIATE_AFTER_SECONDS

    stale = WorkerStateRecord(worker_id=999, status="stopping")
    stale.updated_at = datetime.now() - timedelta(seconds=STALE_INTERMEDIATE_AFTER_SECONDS + 1)
    state_manager._state_cache[999] = stale
    monkeypatch.setattr(fake_db.crud, "get_worker", lambda db, wid: _FakeWorker("stopped"))

    assert await state_manager.transition(999, "starting") is True
    state = await state_manager.get_state(999)
    assert state.status == "starting"


@pytest.mark.asyncio
async def test_transition_self_heals_when_db_also_stale_in_intermediate(state_manager, fake_db, monkeypatch):
    """回归：缓存与 DB 都残留 stopping（真实卡死现场）→ 水合修正为 stopped 后放行"""
    from datetime import datetime, timedelta

    from worker.worker_state import STALE_INTERMEDIATE_AFTER_SECONDS

    stale = WorkerStateRecord(worker_id=999, status="stopping")
    stale.updated_at = datetime.now() - timedelta(seconds=STALE_INTERMEDIATE_AFTER_SECONDS + 1)
    state_manager._state_cache[999] = stale
    monkeypatch.setattr(fake_db.crud, "get_worker", lambda db, wid: _FakeWorker("stopping"))

    assert await state_manager.transition(999, "starting") is True


@pytest.mark.asyncio
async def test_transition_still_rejects_fresh_intermediate_cache(state_manager, fake_db, monkeypatch):
    """进行中的过渡（缓存新鲜）不做自愈，stopping→starting 仍拒绝"""
    state_manager._state_cache[999] = WorkerStateRecord(worker_id=999, status="stopping")
    monkeypatch.setattr(fake_db.crud, "get_worker", lambda db, wid: _FakeWorker("stopped"))

    assert await state_manager.transition(999, "starting") is False
