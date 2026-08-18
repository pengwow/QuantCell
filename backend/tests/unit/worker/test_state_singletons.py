"""
测试 state.py 中的模块级单例
"""

from unittest.mock import AsyncMock

import pytest


class TestConnectionManager:
    """ConnectionManager 单元测试"""

    def test_singleton_instance(self):
        """验证模块级单例存在"""
        from worker.state import connection_manager

        assert connection_manager is not None
        assert hasattr(connection_manager, "active_connections")
        assert connection_manager.connection_count == 0

    @pytest.mark.asyncio
    async def test_connect_and_disconnect(self):
        """测试连接和断开"""
        from worker.state import connection_manager

        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()

        await connection_manager.connect(mock_ws)
        assert connection_manager.connection_count == 1

        connection_manager.disconnect(mock_ws)
        assert connection_manager.connection_count == 0

    @pytest.mark.asyncio
    async def test_broadcast(self):
        """测试广播到所有连接"""
        from worker.state import connection_manager

        ws1 = AsyncMock()
        ws2 = AsyncMock()
        ws1.accept = AsyncMock()
        ws2.accept = AsyncMock()
        ws1.send_json = AsyncMock()
        ws2.send_json = AsyncMock()

        await connection_manager.connect(ws1)
        await connection_manager.connect(ws2)

        message = {"type": "test", "data": "hello"}
        await connection_manager.broadcast(message)

        ws1.send_json.assert_called_once_with(message)
        ws2.send_json.assert_called_once_with(message)

        connection_manager.disconnect(ws1)
        connection_manager.disconnect(ws2)

    @pytest.mark.asyncio
    async def test_broadcast_cleans_disconnected(self):
        """测试广播时自动清理断开连接"""
        from worker.state import connection_manager

        ws1 = AsyncMock()
        ws2 = AsyncMock()
        ws1.accept = AsyncMock()
        ws2.accept = AsyncMock()
        ws1.send_json = AsyncMock()
        ws2.send_json = AsyncMock(side_effect=Exception("disconnected"))

        await connection_manager.connect(ws1)
        await connection_manager.connect(ws2)

        await connection_manager.broadcast({"type": "test"})

        # ws2 应该被自动清理
        assert connection_manager.connection_count == 1

        connection_manager.disconnect(ws1)


class TestStrategyRegistry:
    """StrategyRegistry 单元测试"""

    def test_singleton_instance(self):
        """验证注册表单例存在"""
        from worker.state import strategy_registry

        assert strategy_registry is not None

    def test_register_and_get(self):
        """测试注册和查询策略"""
        from worker.state import StrategyRuntime, strategy_registry

        runtime = StrategyRuntime(
            worker_id=1,
            strategy_id=100,
            name="test_strategy",
            status="stopped",
        )
        strategy_registry.register(runtime)

        retrieved = strategy_registry.get(1)
        assert retrieved is not None
        assert retrieved.name == "test_strategy"
        assert retrieved.status == "stopped"
        assert not retrieved.is_running

        strategy_registry.unregister(1)

    def test_unregister(self):
        """测试注销策略"""
        from worker.state import StrategyRuntime, strategy_registry

        runtime = StrategyRuntime(worker_id=2, strategy_id=200, name="temp")
        strategy_registry.register(runtime)
        assert strategy_registry.get(2) is not None

        removed = strategy_registry.unregister(2)
        assert removed is not None
        assert strategy_registry.get(2) is None

        removed2 = strategy_registry.unregister(999)
        assert removed2 is None

    def test_list_all(self):
        """测试列出所有策略"""
        from worker.state import StrategyRuntime, strategy_registry

        r1 = StrategyRuntime(worker_id=10, strategy_id=1000, name="s1")
        r2 = StrategyRuntime(worker_id=20, strategy_id=2000, name="s2")

        strategy_registry.register(r1)
        strategy_registry.register(r2)

        all_strategies = strategy_registry.list_all()
        assert len(all_strategies) >= 2

        strategy_registry.unregister(10)
        strategy_registry.unregister(20)

    def test_update_status(self):
        """测试状态更新"""
        from worker.state import StrategyRuntime, strategy_registry

        runtime = StrategyRuntime(worker_id=5, strategy_id=500, name="s5")
        strategy_registry.register(runtime)

        strategy_registry.update_status(5, "running")
        assert runtime.status == "running"

        strategy_registry.update_status(5, "error", error_message="test error")
        assert runtime.status == "error"
        assert runtime.error_message == "test error"

        strategy_registry.unregister(5)

    def test_update_nonexistent(self):
        """测试更新不存在的策略"""
        from worker.state import strategy_registry

        result = strategy_registry.update_status(999, "running")
        assert result is None

    def test_on_change_callback(self):
        """测试状态变更回调"""
        from worker.state import StrategyRuntime, strategy_registry

        callback_calls = []

        def callback(worker_id, old_status, new_status, error_msg):
            callback_calls.append((worker_id, old_status, new_status, error_msg))

        strategy_registry.on_change(callback)

        runtime = StrategyRuntime(worker_id=6, strategy_id=600, name="s6")
        strategy_registry.register(runtime)
        strategy_registry.update_status(6, "running")

        assert len(callback_calls) >= 1
        assert callback_calls[0][0] == 6
        assert callback_calls[0][2] == "running"

        # 清理回调
        strategy_registry._change_callbacks.clear()
        strategy_registry.unregister(6)


class TestStrategyRuntime:
    """StrategyRuntime 数据类测试"""

    def test_to_dict(self):
        """测试转换为字典"""
        from worker.state import StrategyRuntime

        runtime = StrategyRuntime(worker_id=1, strategy_id=10, name="test")
        d = runtime.to_dict()
        assert d["worker_id"] == 1
        assert d["strategy_id"] == 10
        assert d["name"] == "test"
        assert d["status"] == "stopped"
        assert not d["is_running"]

    def test_is_running_false_when_no_task(self):
        """测试无任务时 is_running 为 False"""
        from worker.state import StrategyRuntime

        runtime = StrategyRuntime(worker_id=1, strategy_id=10, name="test", status="running")
        assert not runtime.is_running
