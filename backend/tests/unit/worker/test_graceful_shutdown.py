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
