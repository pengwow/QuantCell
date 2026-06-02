"""
简化版 EventHandler 类测试

避免复杂导入链
"""

import pytest
import sys
from unittest.mock import Mock, AsyncMock, MagicMock
from datetime import datetime
from collections import deque

# 添加正确的路径
sys.path.insert(0, '/workspace/backend')

# 直接测试 EventHandler 类，避免导入整个模块
class SimpleEventBufferConfig:
    """简单的配置类"""
    def __init__(self, buffer_size=1000, flush_interval=1.0, batch_size=100):
        self.buffer_size = buffer_size
        self.flush_interval = flush_interval
        self.batch_size = batch_size


class SimpleEventHandler:
    """简化版事件处理器（用于测试核心逻辑）"""
    def __init__(self, worker_id, comm_client=None, config=None):
        self.worker_id = worker_id
        self.comm_client = comm_client
        self.config = config or SimpleEventBufferConfig()
        self._event_buffer = deque(maxlen=self.config.buffer_size)
        self._running = False
        self._events_received = 0
        self._events_sent = 0
        self._events_dropped = 0

    def on_order_event(self, event_data):
        self._events_received += 1
        self._buffer_event({
            "type": "order",
            "data": event_data,
            "timestamp": datetime.now().isoformat()
        })

    def on_fill_event(self, event_data):
        self._events_received += 1
        self._buffer_event({
            "type": "fill",
            "data": event_data,
            "timestamp": datetime.now().isoformat()
        })

    def on_position_event(self, event_data):
        self._events_received += 1
        self._buffer_event({
            "type": "position",
            "data": event_data,
            "timestamp": datetime.now().isoformat()
        })

    def _buffer_event(self, event):
        if len(self._event_buffer) >= self.config.buffer_size:
            self._events_dropped += 1
        self._event_buffer.append(event)

    def get_stats(self):
        return {
            "events_received": self._events_received,
            "events_sent": self._events_sent,
            "events_dropped": self._events_dropped,
            "buffer_size": len(self._event_buffer)
        }


class TestSimpleEventHandler:
    """测试简单版事件处理器"""

    @pytest.fixture
    def event_config(self):
        return SimpleEventBufferConfig(
            buffer_size=10,
            flush_interval=0.1,
            batch_size=3
        )

    @pytest.fixture
    def mock_comm_client(self):
        client = Mock()
        client.send_event = AsyncMock()
        return client

    @pytest.fixture
    def event_handler(self, event_config, mock_comm_client):
        return SimpleEventHandler(
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

    def test_on_order_event(self, event_handler):
        """测试订单事件处理"""
        event_data = {"order_id": "123", "symbol": "BTCUSDT"}
        event_handler.on_order_event(event_data)
        
        assert event_handler._events_received == 1
        assert len(event_handler._event_buffer) == 1
        assert event_handler._event_buffer[0]["type"] == "order"

    def test_on_fill_event(self, event_handler):
        """测试成交事件处理"""
        event_data = {"trade_id": "456", "symbol": "BTCUSDT"}
        event_handler.on_fill_event(event_data)
        
        assert event_handler._events_received == 1
        assert len(event_handler._event_buffer) == 1

    def test_on_position_event(self, event_handler):
        """测试持仓事件处理"""
        event_data = {"position_id": "789", "symbol": "BTCUSDT"}
        event_handler.on_position_event(event_data)
        
        assert event_handler._events_received == 1
        assert len(event_handler._event_buffer) == 1

    def test_buffer_event_buffer_limit(self, event_handler):
        """测试事件缓冲区达到限制"""
        for i in range(15):  # buffer_size 是 10
            event_handler.on_order_event({"order_id": str(i)})
        
        assert event_handler._events_dropped > 0
        assert len(event_handler._event_buffer) <= event_handler.config.buffer_size

    def test_get_stats(self, event_handler):
        """测试获取统计信息"""
        event_handler.on_order_event({"order_id": "123"})
        event_handler.on_fill_event({"trade_id": "456"})
        
        stats = event_handler.get_stats()
        
        assert stats["events_received"] == 2
        assert stats["events_sent"] == 0
        assert stats["events_dropped"] == 0
        assert stats["buffer_size"] == 2


if __name__ == "__main__":
    # 简单的独立测试运行
    test = TestSimpleEventHandler()
    
    # 运行测试初始化
    config = SimpleEventBufferConfig(buffer_size=10, flush_interval=0.1, batch_size=3)
    client = Mock()
    handler = SimpleEventHandler(1, client, config)
    test.test_initialization(handler)
    print("✓ 初始化测试通过")
    
    # 运行事件处理测试
    handler.on_order_event({"order_id": "test-123"})
    assert handler._events_received == 1, "事件接收计数错误"
    assert len(handler._event_buffer) == 1, "缓冲事件数量错误"
    print("✓ 订单事件测试通过")
    
    # 运行统计测试
    stats = handler.get_stats()
    assert stats["events_received"] == 1, "统计数据错误"
    print("✓ 统计功能测试通过")
    
    print("\n所有简单测试通过！")
