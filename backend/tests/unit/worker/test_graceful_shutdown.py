import asyncio

import pytest

from worker.graceful_shutdown import (
    GracefulShutdownManager,
    ShutdownConfig,
    ShutdownPhase,
    ShutdownStatus,
    get_shutdown_manager,
    reset_shutdown_manager,
)


@pytest.fixture
def reset_manager():
    reset_shutdown_manager()
    yield
    reset_shutdown_manager()


def test_shutdown_manager_initialization():
    """测试停机管理器初始化"""
    manager = GracefulShutdownManager()
    assert manager is not None
    assert isinstance(manager.config, ShutdownConfig)


def test_shutdown_status_initialization():
    """测试停机状态初始化"""
    status = ShutdownStatus()
    assert status.phase == ShutdownPhase.REQUESTED
    assert status.phases_completed == 0


def test_get_shutdown_manager_singleton(reset_manager):
    """测试全局停机管理器单例"""
    mgr1 = get_shutdown_manager()
    mgr2 = get_shutdown_manager()
    assert mgr1 is mgr2


@pytest.mark.asyncio
async def test_basic_shutdown():
    """测试基本停机流程"""
    called = []

    async def on_drain():
        called.append("drain")

    async def on_stop_services():
        called.append("stop_services")

    async def on_cleanup():
        called.append("cleanup")

    config = ShutdownConfig(
        total_timeout=5.0,
        drain_timeout=1.0,
        service_stop_timeout=1.0,
        force_kill_after_timeout=False,
    )
    manager = GracefulShutdownManager(
        config=config,
        on_drain=on_drain,
        on_stop_services=on_stop_services,
        on_cleanup=on_cleanup,
    )
    status = await manager.shutdown()

    assert status.is_successful is True
    assert status.phases_completed == 3
    assert called == ["drain", "stop_services", "cleanup"]


@pytest.mark.asyncio
async def test_shutdown_with_timeout():
    """测试超时的停机流程"""
    called = []

    async def slow_drain():
        await asyncio.sleep(0.1)
        called.append("slow_drain")

    config = ShutdownConfig(
        total_timeout=0.05,
        drain_timeout=0.02,
        force_kill_after_timeout=False,
    )
    manager = GracefulShutdownManager(config=config, on_drain=slow_drain)

    status = await manager.shutdown()
    assert status.timeout_occurred is False
    assert status.errors  # Should have timeout error


@pytest.mark.asyncio
async def test_shutdown_skip_phases():
    """测试跳过阶段的停机流程"""
    called = []

    async def on_cleanup():
        called.append("cleanup")

    config = ShutdownConfig(
        total_timeout=5.0,
        skip_drain=True,
        skip_service_stop=True,
        force_kill_after_timeout=False,
    )
    manager = GracefulShutdownManager(config=config, on_cleanup=on_cleanup)

    status = await manager.shutdown()

    assert status.is_successful is True
    assert status.phases_completed == 1
    assert called == ["cleanup"]


def test_shutdown_status_to_dict():
    """测试停机状态转字典"""
    status = ShutdownStatus()
    status_dict = status.to_dict()
    assert "phase" in status_dict
    assert "duration_seconds" in status_dict
    assert "is_successful" in status_dict


def test_shutdown_phase_values_are_lowercase():
    """契约：枚举 value 全小写，防止回归到大写字符串（大小写不一致曾导致阶段设置静默失效）。"""
    for phase in ShutdownPhase:
        assert phase.value == phase.value.lower()


@pytest.mark.asyncio
async def test_phase_names_recorded_as_enum_values():
    """回归：各阶段以枚举 value（小写）记录并推进 status.phase。

    修复前 `_execute_phase_with_timeout` 用大写字符串构造 ShutdownPhase 必抛 ValueError，
    被 except 吞掉，导致 status.phase 停在 DRAINING、且每阶段打一条假 warning。
    """

    async def noop():
        pass

    config = ShutdownConfig(
        total_timeout=5.0,
        drain_timeout=1.0,
        service_stop_timeout=1.0,
        force_kill_after_timeout=False,
    )
    manager = GracefulShutdownManager(config=config, on_drain=noop, on_stop_services=noop, on_cleanup=noop)
    status = await manager.shutdown()

    assert [pr.phase_name for pr in status.phase_results] == [
        ShutdownPhase.DRAINING.value,
        ShutdownPhase.STOPPING_SERVICES.value,
        ShutdownPhase.CLEANUP.value,
    ]
    assert status.phase == ShutdownPhase.COMPLETED
