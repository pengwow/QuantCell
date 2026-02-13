"""
Realtime模块测试配置

提供测试所需的fixture和工具函数
"""

import pytest
import asyncio
from typing import Dict, Any, List, Optional
from unittest.mock import Mock, AsyncMock

from realtime.abstract_client import AbstractExchangeClient
from realtime.websocket_manager import WebSocketManager
from realtime.data_processor import DataProcessor
from realtime.data_distributor import DataDistributor
from realtime.monitor import RealtimeMonitor
from realtime.config import RealtimeConfig


class MockExchangeClient(AbstractExchangeClient):
    """模拟交易所客户端，用于测试"""
    
    def __init__(self, config: Dict[str, Any], exchange_name: str = "mock_exchange"):
        super().__init__(config)
        self._exchange_name = exchange_name
        self._connected = False
        self._messages = []
        self._parser = Mock()
        
    @property
    def exchange_name(self) -> str:
        return self._exchange_name
    
    @exchange_name.setter
    def exchange_name(self, value: str):
        self._exchange_name = value
    
    async def connect(self) -> bool:
        self._connected = True
        self.connected = True
        return True
    
    async def disconnect(self) -> bool:
        self._connected = False
        self.connected = False
        return True
    
    async def subscribe(self, channels: List[str]) -> bool:
        self.subscribed_channels.update(channels)
        return True
    
    async def unsubscribe(self, channels: List[str]) -> bool:
        for ch in channels:
            self.subscribed_channels.discard(ch)
        return True
    
    async def receive_message(self) -> Optional[Dict[str, Any]]:
        if self._messages:
            return self._messages.pop(0)
        return None
    
    def get_data_parser(self):
        return self._parser
    
    def get_available_channels(self) -> List[str]:
        return ["kline", "depth", "trade"]
    
    def add_mock_message(self, message: Dict[str, Any]):
        """添加模拟消息用于测试"""
        self._messages.append(message)


@pytest.fixture
def mock_config():
    """提供模拟配置"""
    return {
        "api_key": "test_key",
        "api_secret": "test_secret",
        "testnet": True,
        "base_url": "wss://test.example.com/ws"
    }


@pytest.fixture
def mock_exchange_client(mock_config):
    """提供模拟交易所客户端"""
    return MockExchangeClient(mock_config, "test_exchange")


@pytest.fixture
def websocket_manager():
    """提供WebSocket管理器实例"""
    return WebSocketManager()


@pytest.fixture
def data_processor():
    """提供数据处理器实例"""
    return DataProcessor()


@pytest.fixture
def data_distributor():
    """提供数据分发器实例"""
    return DataDistributor()


@pytest.fixture
def realtime_monitor():
    """提供实时监控器实例"""
    return RealtimeMonitor(interval=1)


@pytest.fixture
def realtime_config():
    """提供实时配置实例"""
    return RealtimeConfig()


@pytest.fixture
async def async_websocket_manager():
    """提供异步WebSocket管理器"""
    manager = WebSocketManager()
    yield manager
    # 清理
    for client in list(manager.clients.values()):
        await client.disconnect()


@pytest.fixture
def sample_kline_message():
    """提供示例K线消息"""
    return {
        "data_type": "kline",
        "symbol": "BTCUSDT",
        "interval": "1m",
        "open": 50000.0,
        "high": 50100.0,
        "low": 49900.0,
        "close": 50050.0,
        "volume": 1.5,
        "timestamp": 1234567890
    }


@pytest.fixture
def sample_depth_message():
    """提供示例深度消息"""
    return {
        "data_type": "depth",
        "symbol": "BTCUSDT",
        "bids": [[50000.0, 1.0], [49990.0, 2.0]],
        "asks": [[50010.0, 1.5], [50020.0, 2.5]],
        "timestamp": 1234567890
    }


@pytest.fixture
def sample_trade_message():
    """提供示例交易消息"""
    return {
        "data_type": "trade",
        "symbol": "BTCUSDT",
        "price": 50050.0,
        "quantity": 0.5,
        "side": "buy",
        "timestamp": 1234567890
    }


@pytest.fixture(scope="session")
def event_loop():
    """提供事件循环"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
