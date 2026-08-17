"""
测试 EventHandler 类

测试内容：
1. 事件缓冲和刷新机制
2. 订单/成交/持仓事件处理
3. 统计数据收集
4. 启动/停止功能
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, MagicMock
from datetime import datetime
from collections import deque

from worker.event_handler import EventHandler, EventBufferConfig


class TestEventBufferConfig:
    """测试 EventBufferConfig 类"""

    def test_default_values(self):
        """测试默认配置"""
        config = EventBufferConfig()
        assert config.buffer_size == 1000
        assert config.flush_interval == 1.0
        assert config.batch_size == 100

    def test_custom_values(self):
        """测试自定义配置"""
        config = EventBufferConfig(
            buffer_size=500,
            flush_interval=0.5,
            batch_size=50
        )
        assert config.buffer_size == 500
        assert config.flush_interval == 0.5
        assert config.batch_size == 50


class TestEventHandler:
    """测试 EventHandler 类"""

    @pytest.fixture
    def event_config(self):
        """创建事件缓冲配置"""
        return EventBufferConfig(
            buffer_size=10,
            flush_interval=0.1,
            batch_size=3
        )

    @pytest.fixture
    def mock_comm_client(self):
        """创建模拟的通信客户端"""
        client = Mock()
        client.send_event = AsyncMock()
        return client

    @pytest.fixture
    def event_handler(self, event_config, mock_comm_client):
        """创建 EventHandler 实例"""
        return EventHandler(
            worker_id=1,
            comm_client=mock_comm_client,
            config=event_config
        )

    def test_initialization(self, event_handler):
        """测试初始化"""
        assert event_handler.worker_id == 1
        assert event_handler._running is False
        assert isinstance(event_handler._event_buffer, deque)
        assert event_handler._events_received == 0
        assert event_handler._events_sent == 0
        assert event_handler._events_dropped == 0

    def test_on_order_event(self, event_handler, mock_comm_client):
        """测试订单事件处理"""
        event_data = {"order_id": "123", "symbol": "BTCUSDT"}
        event_handler.on_order_event(event_data)
        
        assert event_handler._events_received == 1
        assert len(event_handler._event_buffer) == 1
        
        # 检查缓冲的事件
        buffered_event = event_handler._event_buffer[0]
        assert buffered_event["type"] == "order"
        assert buffered_event["data"] == event_data
        assert "timestamp" in buffered_event

    def test_on_fill_event(self, event_handler, mock_comm_client):
        """测试成交事件处理"""
        event_data = {"trade_id": "456", "symbol": "BTCUSDT"}
        event_handler.on_fill_event(event_data)
        
        assert event_handler._events_received == 1
        assert len(event_handler._event_buffer) == 1

    def test_on_position_event(self, event_handler, mock_comm_client):
        """测试持仓事件处理"""
        event_data = {"position_id": "789", "symbol": "BTCUSDT"}
        event_handler.on_position_event(event_data)
        
        assert event_handler._events_received == 1
        assert len(event_handler._event_buffer) == 1

    def test_buffer_event_buffer_limit(self, event_handler):
        """测试事件缓冲区达到限制"""
        # 添加足够多的事件来填满缓冲区
        for i in range(15):  # buffer_size 是 10
            event_handler.on_order_event({"order_id": str(i)})
        
        # 检查是否有事件被丢弃
        assert event_handler._events_dropped > 0
        assert len(event_handler._event_buffer) <= event_handler.config.buffer_size

    def test_get_stats(self, event_handler):
        """测试获取统计信息"""
        # 添加一些事件
        event_handler.on_order_event({"order_id": "123"})
        event_handler.on_fill_event({"trade_id": "456"})
        
        stats = event_handler.get_stats()
        
        assert stats["events_received"] == 2
        assert stats["events_sent"] == 0
        assert stats["events_dropped"] == 0
        assert stats["buffer_size"] == 2

    @pytest.mark.asyncio
    async def test_start_stop(self, event_handler):
        """测试启动和停止"""
        # 启动
        await event_handler.start()
        assert event_handler._running is True
        
        # 停止
        await event_handler.stop()
        assert event_handler._running is False

    @pytest.mark.asyncio
    async def test_flush_buffer(self, event_handler, mock_comm_client):
        """测试刷新缓冲区"""
        # 添加一些事件
        event_handler.on_order_event({"order_id": "123"})
        event_handler.on_fill_event({"trade_id": "456"})
        
        # 刷新缓冲区
        await event_handler._flush_buffer()
        
        # 验证事件被发送
        assert mock_comm_client.send_event.call_count == 2
        assert event_handler._events_sent == 2
        assert len(event_handler._event_buffer) == 0


class TestAxonEventHandler:
    """测试 AxonEventHandler 类"""

    @pytest.fixture
    def mock_trader(self):
        """创建模拟的 trader 对象"""
        trader = Mock()
        trader.msg_bus = Mock()
        return trader

    @pytest.fixture
    def event_callback(self):
        """创建事件回调函数"""
        return Mock()

    @pytest.fixture
    def axon_handler(self, mock_trader, event_callback):
        """创建 AxonEventHandler 实例"""
        from worker.event_handler import AxonEventHandler
        return AxonEventHandler(mock_trader, event_callback)

    def test_subscribe_events(self, axon_handler, mock_trader):
        """测试事件订阅"""
        axon_handler.subscribe_events()
        
        # 验证订阅了正确的事件
        assert mock_trader.msg_bus.subscribe.call_count == 3
        assert axon_handler._subscribed is True

    def test_unsubscribe_events(self, axon_handler, mock_trader):
        """测试事件取消订阅"""
        axon_handler.subscribe_events()
        axon_handler.unsubscribe_events()
        
        # 验证取消了订阅
        assert mock_trader.msg_bus.unsubscribe.call_count == 3
        assert axon_handler._subscribed is False

    def test_convert_order_event(self, axon_handler):
        """测试转换订单事件"""
        event = Mock()
        event.order_id = "test-123"
        event.instrument_id = "BTCUSDT"
        event.side = "BUY"
        event.quantity = 0.01
        event.price = 50000.0
        event.status = "FILLED"
        event.timestamp = datetime.now()
        
        converted = axon_handler._convert_order_event(event)
        
        assert converted["type"] == "order"
        assert converted["order_id"] == "test-123"
        assert converted["instrument_id"] == "BTCUSDT"

    def test_convert_fill_event(self, axon_handler):
        """测试转换成交事件"""
        event = Mock()
        event.order_id = "test-123"
        event.instrument_id = "BTCUSDT"
        event.side = "BUY"
        event.quantity = 0.01
        event.price = 50000.0
        event.commission = 1.0
        event.timestamp = datetime.now()
        
        converted = axon_handler._convert_fill_event(event)
        
        assert converted["type"] == "fill"
        assert converted["order_id"] == "test-123"

    def test_convert_position_event(self, axon_handler):
        """测试转换持仓事件"""
        event = Mock()
        event.instrument_id = "BTCUSDT"
        event.side = "LONG"
        event.quantity = 0.01
        event.avg_price = 50000.0
        event.unrealized_pnl = 100.0
        event.timestamp = datetime.now()
        
        converted = axon_handler._convert_position_event(event)
        
        assert converted["type"] == "position"
        assert converted["instrument_id"] == "BTCUSDT"
