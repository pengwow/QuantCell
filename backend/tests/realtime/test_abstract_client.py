"""
抽象交易所客户端接口测试

测试AbstractExchangeClient的接口定义和Mock实现
"""

import pytest
from typing import Dict, Any, List, Optional

from realtime.abstract_client import AbstractExchangeClient


class TestAbstractExchangeClient:
    """测试抽象交易所客户端接口"""
    
    def test_abstract_class_cannot_be_instantiated(self):
        """测试抽象类不能直接实例化"""
        with pytest.raises(TypeError):
            AbstractExchangeClient({})
    
    def test_concrete_client_can_be_instantiated(self, mock_exchange_client):
        """测试具体实现可以实例化"""
        assert mock_exchange_client is not None
        assert isinstance(mock_exchange_client, AbstractExchangeClient)
    
    def test_initialization(self, mock_exchange_client, mock_config):
        """测试初始化"""
        assert mock_exchange_client.config == mock_config
        assert mock_exchange_client.connected is False
        assert mock_exchange_client.subscribed_channels == set()
    
    def test_exchange_name_property(self, mock_exchange_client):
        """测试交易所名称属性"""
        assert mock_exchange_client.exchange_name == "test_exchange"
        
        # 测试setter
        mock_exchange_client.exchange_name = "new_exchange"
        assert mock_exchange_client.exchange_name == "new_exchange"
    
    @pytest.mark.asyncio
    async def test_connect(self, mock_exchange_client):
        """测试连接"""
        result = await mock_exchange_client.connect()
        assert result is True
        assert mock_exchange_client.connected is True
    
    @pytest.mark.asyncio
    async def test_disconnect(self, mock_exchange_client):
        """测试断开连接"""
        # 先连接
        await mock_exchange_client.connect()
        assert mock_exchange_client.connected is True
        
        # 再断开
        result = await mock_exchange_client.disconnect()
        assert result is True
        assert mock_exchange_client.connected is False
    
    @pytest.mark.asyncio
    async def test_subscribe(self, mock_exchange_client):
        """测试订阅"""
        channels = ["kline_BTCUSDT_1m", "depth_BTCUSDT"]
        result = await mock_exchange_client.subscribe(channels)
        
        assert result is True
        assert "kline_BTCUSDT_1m" in mock_exchange_client.subscribed_channels
        assert "depth_BTCUSDT" in mock_exchange_client.subscribed_channels
    
    @pytest.mark.asyncio
    async def test_unsubscribe(self, mock_exchange_client):
        """测试取消订阅"""
        # 先订阅
        channels = ["kline_BTCUSDT_1m", "depth_BTCUSDT", "trade_BTCUSDT"]
        await mock_exchange_client.subscribe(channels)
        assert len(mock_exchange_client.subscribed_channels) == 3
        
        # 取消部分订阅
        result = await mock_exchange_client.unsubscribe(["kline_BTCUSDT_1m"])
        assert result is True
        assert "kline_BTCUSDT_1m" not in mock_exchange_client.subscribed_channels
        assert "depth_BTCUSDT" in mock_exchange_client.subscribed_channels
    
    @pytest.mark.asyncio
    async def test_receive_message_empty(self, mock_exchange_client):
        """测试接收空消息"""
        message = await mock_exchange_client.receive_message()
        assert message is None
    
    @pytest.mark.asyncio
    async def test_receive_message_with_data(self, mock_exchange_client, sample_kline_message):
        """测试接收消息"""
        mock_exchange_client.add_mock_message(sample_kline_message)
        
        message = await mock_exchange_client.receive_message()
        assert message is not None
        assert message["data_type"] == "kline"
        assert message["symbol"] == "BTCUSDT"
    
    def test_get_data_parser(self, mock_exchange_client):
        """测试获取数据解析器"""
        parser = mock_exchange_client.get_data_parser()
        assert parser is not None
    
    def test_get_available_channels(self, mock_exchange_client):
        """测试获取可用频道"""
        channels = mock_exchange_client.get_available_channels()
        assert isinstance(channels, list)
        assert len(channels) > 0
        assert "kline" in channels


class TestAbstractClientEdgeCases:
    """测试边界条件和异常场景"""
    
    def test_empty_config(self):
        """测试空配置"""
        from tests.realtime.conftest import MockExchangeClient
        client = MockExchangeClient({})
        assert client.config == {}
    
    def test_none_config(self):
        """测试None配置"""
        from tests.realtime.conftest import MockExchangeClient
        client = MockExchangeClient(None)
        assert client.config is None
    
    @pytest.mark.asyncio
    async def test_subscribe_empty_list(self, mock_exchange_client):
        """测试订阅空列表"""
        result = await mock_exchange_client.subscribe([])
        assert result is True
        assert len(mock_exchange_client.subscribed_channels) == 0
    
    @pytest.mark.asyncio
    async def test_unsubscribe_not_subscribed(self, mock_exchange_client):
        """测试取消未订阅的频道"""
        # 订阅一个频道
        await mock_exchange_client.subscribe(["kline_BTCUSDT_1m"])
        
        # 取消未订阅的频道
        result = await mock_exchange_client.unsubscribe(["depth_BTCUSDT"])
        assert result is True
        # 原有订阅不应受影响
        assert "kline_BTCUSDT_1m" in mock_exchange_client.subscribed_channels
    
    @pytest.mark.asyncio
    async def test_multiple_connect_disconnect(self, mock_exchange_client):
        """测试多次连接断开"""
        # 第一次连接
        await mock_exchange_client.connect()
        assert mock_exchange_client.connected is True
        
        # 第二次连接（应该仍然成功）
        await mock_exchange_client.connect()
        assert mock_exchange_client.connected is True
        
        # 第一次断开
        await mock_exchange_client.disconnect()
        assert mock_exchange_client.connected is False
        
        # 第二次断开（应该仍然成功）
        await mock_exchange_client.disconnect()
        assert mock_exchange_client.connected is False
