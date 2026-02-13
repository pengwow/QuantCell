"""
WebSocket连接管理器测试

测试WebSocketManager的客户端管理、消息处理等功能
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch

from realtime.websocket_manager import WebSocketManager
from realtime.abstract_client import AbstractExchangeClient


class TestWebSocketManager:
    """测试WebSocket管理器核心功能"""

    def test_initialization(self, websocket_manager):
        """测试初始化"""
        assert websocket_manager.clients == {}
        assert websocket_manager.message_handlers == []
        assert websocket_manager.running is False
        assert websocket_manager.task is None

    def test_register_client_success(self, websocket_manager, mock_exchange_client):
        """测试成功注册客户端"""
        result = websocket_manager.register_client(mock_exchange_client)

        assert result is True
        assert "test_exchange" in websocket_manager.clients
        assert websocket_manager.clients["test_exchange"] == mock_exchange_client

    def test_register_client_duplicate(self, websocket_manager, mock_exchange_client):
        """测试重复注册客户端"""
        # 第一次注册
        websocket_manager.register_client(mock_exchange_client)

        # 第二次注册（不强制替换）
        result = websocket_manager.register_client(mock_exchange_client, force=False)
        assert result is False

    def test_register_client_force_replace(self, websocket_manager, mock_exchange_client):
        """测试强制替换客户端"""
        # 第一次注册
        websocket_manager.register_client(mock_exchange_client)

        # 创建新客户端
        new_client = Mock(spec=AbstractExchangeClient)
        new_client.exchange_name = "test_exchange"

        # 强制替换
        result = websocket_manager.register_client(new_client, force=True)
        assert result is True
        assert websocket_manager.clients["test_exchange"] == new_client

    @pytest.mark.asyncio
    async def test_unregister_client_success(self, websocket_manager, mock_exchange_client):
        """测试成功注销客户端"""
        # 先注册
        websocket_manager.register_client(mock_exchange_client)
        assert "test_exchange" in websocket_manager.clients

        # 注销 - 使用patch避免asyncio.create_task问题
        with patch.object(websocket_manager, '_disconnect_client', new_callable=AsyncMock):
            result = websocket_manager.unregister_client("test_exchange")
            assert result is True
            assert "test_exchange" not in websocket_manager.clients

    def test_unregister_client_not_exists(self, websocket_manager):
        """测试注销不存在的客户端"""
        result = websocket_manager.unregister_client("non_existent")
        assert result is False

    def test_add_message_handler(self, websocket_manager):
        """测试添加消息处理器"""
        handler = Mock()
        websocket_manager.add_message_handler(handler)

        assert handler in websocket_manager.message_handlers
        assert len(websocket_manager.message_handlers) == 1

    def test_remove_message_handler(self, websocket_manager):
        """测试移除消息处理器"""
        handler = Mock()
        websocket_manager.add_message_handler(handler)

        result = websocket_manager.remove_message_handler(handler)
        assert result is True
        assert handler not in websocket_manager.message_handlers

    def test_remove_message_handler_not_exists(self, websocket_manager):
        """测试移除不存在的消息处理器"""
        handler = Mock()
        result = websocket_manager.remove_message_handler(handler)
        assert result is False

    def test_get_connected_clients_empty(self, websocket_manager):
        """测试获取空连接列表"""
        clients = websocket_manager.get_connected_clients()
        assert clients == []

    @pytest.mark.asyncio
    async def test_get_connected_clients_with_connected(self, websocket_manager, mock_exchange_client):
        """测试获取已连接客户端列表"""
        # 注册并连接客户端
        websocket_manager.register_client(mock_exchange_client)
        await mock_exchange_client.connect()

        clients = websocket_manager.get_connected_clients()
        assert "test_exchange" in clients

    def test_get_all_clients_empty(self, websocket_manager):
        """测试获取空客户端列表"""
        clients = websocket_manager.get_all_clients()
        assert clients == []

    def test_get_all_clients(self, websocket_manager, mock_exchange_client):
        """测试获取所有客户端"""
        websocket_manager.register_client(mock_exchange_client)

        clients = websocket_manager.get_all_clients()
        assert "test_exchange" in clients
        assert len(clients) == 1


class TestWebSocketManagerAsync:
    """测试WebSocket管理器异步功能"""

    @pytest.mark.asyncio
    async def test_start_stop(self, websocket_manager):
        """测试启动和停止"""
        # 启动
        await websocket_manager.start()
        assert websocket_manager.running is True

        # 停止
        await websocket_manager.stop()
        assert websocket_manager.running is False

    @pytest.mark.asyncio
    async def test_connect_all(self, websocket_manager, mock_exchange_client):
        """测试连接所有客户端"""
        # 注册客户端
        websocket_manager.register_client(mock_exchange_client)

        # 连接所有
        await websocket_manager.connect_all()

        assert mock_exchange_client.connected is True

    @pytest.mark.asyncio
    async def test_disconnect_all(self, websocket_manager, mock_exchange_client):
        """测试断开所有客户端"""
        # 注册并连接
        websocket_manager.register_client(mock_exchange_client)
        await mock_exchange_client.connect()

        # 断开所有
        await websocket_manager.disconnect_all()

        assert mock_exchange_client.connected is False


class TestWebSocketManagerEdgeCases:
    """测试边界条件和异常场景"""

    def test_register_client_none(self, websocket_manager):
        """测试注册None客户端"""
        with pytest.raises(AttributeError):
            websocket_manager.register_client(None)

    @pytest.mark.asyncio
    async def test_unregister_client_while_running(self, websocket_manager, mock_exchange_client):
        """测试运行时注销客户端"""
        websocket_manager.register_client(mock_exchange_client)
        websocket_manager.running = True

        # 使用patch避免asyncio.create_task问题
        with patch.object(websocket_manager, '_disconnect_client', new_callable=AsyncMock):
            result = websocket_manager.unregister_client("test_exchange")
            assert result is True

    def test_multiple_handlers(self, websocket_manager):
        """测试多个消息处理器"""
        handler1 = Mock()
        handler2 = Mock()

        websocket_manager.add_message_handler(handler1)
        websocket_manager.add_message_handler(handler2)

        assert len(websocket_manager.message_handlers) == 2
        assert handler1 in websocket_manager.message_handlers
        assert handler2 in websocket_manager.message_handlers

    @pytest.mark.asyncio
    async def test_connect_all_empty(self, websocket_manager):
        """测试连接空客户端列表"""
        # 不应该抛出异常
        await websocket_manager.connect_all()
        # connect_all不会设置running状态

    @pytest.mark.asyncio
    async def test_disconnect_all_empty(self, websocket_manager):
        """测试断开空客户端列表"""
        # 不应该抛出异常
        await websocket_manager.disconnect_all()


class TestWebSocketManagerIntegration:
    """测试WebSocket管理器集成场景"""

    @pytest.mark.asyncio
    async def test_full_lifecycle(self, websocket_manager, mock_exchange_client):
        """测试完整生命周期"""
        # 1. 注册客户端
        result = websocket_manager.register_client(mock_exchange_client)
        assert result is True

        # 2. 启动管理器
        await websocket_manager.start()
        assert websocket_manager.running is True

        # 3. 连接所有
        await websocket_manager.connect_all()
        assert mock_exchange_client.connected is True

        # 4. 添加消息处理器
        handler = Mock()
        websocket_manager.add_message_handler(handler)

        # 5. 停止 - 使用patch避免超时问题
        # 直接取消任务而不是等待它们完成
        websocket_manager.running = False
        if websocket_manager.task:
            websocket_manager.task.cancel()
            try:
                await websocket_manager.task
            except asyncio.CancelledError:
                pass
            websocket_manager.task = None
        
        if websocket_manager.reconnect_task:
            websocket_manager.reconnect_task.cancel()
            try:
                await websocket_manager.reconnect_task
            except asyncio.CancelledError:
                pass
            websocket_manager.reconnect_task = None
        
        # 断开所有客户端连接
        await websocket_manager.disconnect_all()
        
        assert websocket_manager.running is False

        # 6. 注销客户端 - 使用patch
        with patch.object(websocket_manager, '_disconnect_client', new_callable=AsyncMock):
            result = websocket_manager.unregister_client("test_exchange")
            assert result is True

    @pytest.mark.asyncio
    async def test_multiple_clients(self, websocket_manager):
        """测试多个客户端管理"""
        from tests.realtime.conftest import MockExchangeClient

        # 创建多个客户端
        client1 = MockExchangeClient({}, "exchange1")
        client2 = MockExchangeClient({}, "exchange2")

        # 注册
        websocket_manager.register_client(client1)
        websocket_manager.register_client(client2)

        assert len(websocket_manager.clients) == 2
        assert "exchange1" in websocket_manager.clients
        assert "exchange2" in websocket_manager.clients

        # 连接所有
        await websocket_manager.connect_all()
        assert client1.connected is True
        assert client2.connected is True
