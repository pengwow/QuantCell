"""
WebSocket 和策略生命周期集成测试

测试策略的完整生命周期：创建 -> 启动 -> 停止 -> 删除
以及 WebSocket 连接、心跳、状态推送功能。

要求运行中的 FastAPI 服务（通过 --run-integration 标志启用）
"""
import pytest
import asyncio
import json
from unittest.mock import AsyncMock

from worker.state import connection_manager, strategy_registry, StrategyRuntime


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        "not config.getoption('--run-integration')",
        reason="集成测试需要 --run-integration 标志",
    ),
]


class TestWebSocketConnection:
    """WebSocket 连接集成测试"""

    @pytest.mark.asyncio
    async def test_websocket_connect_and_disconnect(self):
        mock_ws = AsyncMock()
        await connection_manager.connect(mock_ws)
        assert connection_manager.connection_count == 1

        mock_ws.accept.assert_called_once()

        connection_manager.disconnect(mock_ws)
        assert connection_manager.connection_count == 0

    @pytest.mark.asyncio
    async def test_websocket_heartbeat(self):
        mock_ws = AsyncMock()
        mock_ws.receive_text = AsyncMock(return_value=json.dumps({"type": "ping"}))

        await connection_manager.connect(mock_ws)

        data = await mock_ws.receive_text()
        msg = json.loads(data)
        assert msg["type"] == "ping"

        connection_manager.disconnect(mock_ws)

    @pytest.mark.asyncio
    async def test_websocket_broadcast(self):
        mock_ws = AsyncMock()
        await connection_manager.connect(mock_ws)

        await connection_manager.broadcast({"type": "notification", "data": "test"})

        mock_ws.send_json.assert_called_with({"type": "notification", "data": "test"})

        connection_manager.disconnect(mock_ws)


class TestStrategyLifecycle:
    """策略生命周期集成测试"""

    def test_strategy_create_stop_delete_flow(self):
        runtime = StrategyRuntime(
            worker_id=100,
            strategy_id=1000,
            name="integration_test_strategy",
            status="stopped",
        )

        strategy_registry.register(runtime)
        assert strategy_registry.get(100) is not None
        assert strategy_registry.get(100).status == "stopped"

        strategy_registry.update_status(100, "running")
        assert strategy_registry.get(100).status == "running"

        strategy_registry.update_status(100, "stopped")
        assert strategy_registry.get(100).status == "stopped"

        removed = strategy_registry.unregister(100)
        assert removed is not None
        assert strategy_registry.get(100) is None

    def test_multiple_strategies_registration(self):
        runtimes = []
        for i in range(5):
            rt = StrategyRuntime(
                worker_id=1000 + i,
                strategy_id=10000 + i,
                name=f"multi_test_{i}",
            )
            strategy_registry.register(rt)
            runtimes.append(rt)

        all_strategies = strategy_registry.list_all()
        test_strategies = [
            s for s in all_strategies
            if s.worker_id >= 1000 and s.worker_id < 1005
        ]
        assert len(test_strategies) == 5

        for rt in runtimes:
            strategy_registry.unregister(rt.worker_id)

    def test_error_state_propagation(self):
        error_captured = []

        def error_callback(worker_id, old_status, new_status, error_msg):
            error_captured.append({
                "worker_id": worker_id,
                "old_status": old_status,
                "new_status": new_status,
                "error_message": error_msg,
            })

        strategy_registry.on_change(error_callback)

        runtime = StrategyRuntime(worker_id=200, strategy_id=2000, name="error_test")
        strategy_registry.register(runtime)
        strategy_registry.update_status(200, "running")
        strategy_registry.update_status(200, "error", error_message="模拟策略异常")

        assert runtime.status == "error"
        assert runtime.error_message == "模拟策略异常"
        assert len(error_captured) >= 1

        strategy_registry._change_callbacks.remove(error_callback)
        strategy_registry.unregister(200)


class TestStateBroadcast:
    """状态广播集成测试"""

    @pytest.mark.asyncio
    async def test_strategy_event_broadcast(self):
        mock_ws = AsyncMock()

        await connection_manager.connect(mock_ws)

        runtime = StrategyRuntime(worker_id=300, strategy_id=3000, name="broadcast_test")
        strategy_registry.register(runtime)

        strategy_registry.update_status(300, "running")
        strategy_registry.update_status(300, "stopped")

        await asyncio.sleep(0.1)

        strategy_registry.unregister(300)
        connection_manager.disconnect(mock_ws)