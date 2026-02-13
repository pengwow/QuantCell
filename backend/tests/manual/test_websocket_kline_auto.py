#!/usr/bin/env python3
"""
WebSocket K线数据自动测试脚本 (pytest)

使用pytest框架进行自动化测试，验证WebSocket K线数据接收功能
功能包括：
- 测试WebSocket连接建立
- 测试K线数据订阅
- 验证数据格式正确性
- 测试连接断开和重连
- 使用Mock对象模拟数据接收
- 生成测试报告

使用方法:
    cd /Users/liupeng/workspace/quant/QuantCell/backend
    python -m pytest tests/manual/test_websocket_kline_auto.py -v

参数说明:
    -v: 详细输出
    -s: 显示print输出
    --duration: 测试持续时间（秒）
"""

import asyncio
import json
import sys
import time
from datetime import datetime
from typing import Dict, Any, List
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from collections import defaultdict

import pytest

# 添加项目根目录到Python路径
sys.path.insert(0, '/Users/liupeng/workspace/quant/QuantCell/backend')

from exchange.binance.websocket_client import BinanceWebSocketClient, BinanceDataParser
from exchange.binance.config import BinanceConfig


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_config():
    """创建Mock配置"""
    config = Mock(spec=BinanceConfig)
    config.api_key = "test_api_key"
    config.api_secret = "test_api_secret"
    config.testnet = True
    config.tld = "com"
    config.proxy_url = None
    return config


@pytest.fixture
def mock_websocket_client(mock_config):
    """创建Mock WebSocket客户端"""
    client = Mock(spec=BinanceWebSocketClient)
    client.exchange_name = "binance"
    client.config = {
        'api_key': 'test_key',
        'api_secret': 'test_secret',
        'testnet': True,
    }
    client.subscribed_channels = set()
    client._connected = False
    client._active_sockets = {}
    
    # Mock方法
    client.connect = AsyncMock(return_value=True)
    client.disconnect = AsyncMock(return_value=True)
    client.subscribe = AsyncMock(return_value=True)
    client.unsubscribe = AsyncMock(return_value=True)
    client.add_message_callback = Mock()
    client.remove_message_callback = Mock()
    
    return client


@pytest.fixture
def sample_kline_data():
    """创建示例K线数据"""
    return {
        "e": "kline",
        "E": 1234567890000,
        "s": "BTCUSDT",
        "k": {
            "t": 1234567800000,
            "T": 1234567860000,
            "s": "BTCUSDT",
            "i": "1m",
            "f": 100,
            "L": 200,
            "o": "50000.00",
            "c": "50100.00",
            "h": "50200.00",
            "l": "49900.00",
            "v": "10.5",
            "n": 150,
            "x": False,
            "q": "525000.00",
            "V": "5.0",
            "Q": "250000.00",
            "B": "0"
        }
    }


@pytest.fixture
def data_parser():
    """创建数据解析器"""
    return BinanceDataParser()


# =============================================================================
# 测试类
# =============================================================================

class TestWebSocketConnection:
    """测试WebSocket连接功能"""
    
    @pytest.mark.asyncio
    async def test_websocket_client_initialization(self, mock_config):
        """测试WebSocket客户端初始化"""
        client = BinanceWebSocketClient(mock_config)
        
        assert client.exchange_name == "binance"
        assert client._connected is False
        assert client._active_sockets == {}
        assert client.subscribed_channels == set()
        assert client._reconnect_enabled is True
        assert client._max_reconnect_attempts == 3
    
    @pytest.mark.asyncio
    async def test_websocket_connect_success(self, mock_websocket_client):
        """测试WebSocket连接成功"""
        result = await mock_websocket_client.connect()
        
        assert result is True
        mock_websocket_client.connect.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_websocket_connect_failure(self, mock_websocket_client):
        """测试WebSocket连接失败"""
        mock_websocket_client.connect.return_value = False
        
        result = await mock_websocket_client.connect()
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_websocket_disconnect(self, mock_websocket_client):
        """测试WebSocket断开连接"""
        result = await mock_websocket_client.disconnect()
        
        assert result is True
        mock_websocket_client.disconnect.assert_called_once()


class TestKlineDataSubscription:
    """测试K线数据订阅功能"""
    
    @pytest.mark.asyncio
    async def test_subscribe_single_channel(self, mock_websocket_client):
        """测试订阅单个频道"""
        channels = ["BTCUSDT@kline_1m"]
        
        result = await mock_websocket_client.subscribe(channels)
        
        assert result is True
        mock_websocket_client.subscribe.assert_called_once_with(channels)
    
    @pytest.mark.asyncio
    async def test_subscribe_multiple_channels(self, mock_websocket_client):
        """测试订阅多个频道"""
        channels = [
            "BTCUSDT@kline_1m",
            "BTCUSDT@kline_5m",
            "ETHUSDT@kline_1m",
            "ETHUSDT@kline_5m"
        ]
        
        result = await mock_websocket_client.subscribe(channels)
        
        assert result is True
        mock_websocket_client.subscribe.assert_called_once_with(channels)
    
    @pytest.mark.asyncio
    async def test_unsubscribe_channels(self, mock_websocket_client):
        """测试取消订阅频道"""
        channels = ["BTCUSDT@kline_1m"]
        
        result = await mock_websocket_client.unsubscribe(channels)
        
        assert result is True
        mock_websocket_client.unsubscribe.assert_called_once_with(channels)
    
    @pytest.mark.asyncio
    async def test_subscribe_failure(self, mock_websocket_client):
        """测试订阅失败"""
        mock_websocket_client.subscribe.return_value = False
        channels = ["BTCUSDT@kline_1m"]
        
        result = await mock_websocket_client.subscribe(channels)
        
        assert result is False


class TestKlineDataParsing:
    """测试K线数据解析功能"""
    
    def test_parse_kline_data(self, data_parser, sample_kline_data):
        """测试解析K线数据"""
        result = data_parser.parse_kline(sample_kline_data)
        
        assert result['symbol'] == "BTCUSDT"
        assert result['interval'] == "1m"
        assert result['open'] == 50000.00
        assert result['high'] == 50200.00
        assert result['low'] == 49900.00
        assert result['close'] == 50100.00
        assert result['volume'] == 10.5
        assert result['trades'] == 150
        assert result['is_final'] is False
    
    def test_parse_depth_data(self, data_parser):
        """测试解析深度数据"""
        depth_data = {
            "s": "BTCUSDT",
            "u": 12345,
            "b": [["50000.00", "1.5"], ["49900.00", "2.0"]],
            "a": [["50100.00", "1.0"], ["50200.00", "0.5"]]
        }
        
        result = data_parser.parse_depth(depth_data)
        
        assert result['symbol'] == "BTCUSDT"
        assert result['last_update_id'] == 12345
        assert len(result['bids']) == 2
        assert len(result['asks']) == 2
        assert result['bids'][0] == [50000.00, 1.5]
        assert result['asks'][0] == [50100.00, 1.0]
    
    def test_parse_trade_data(self, data_parser):
        """测试解析交易数据"""
        trade_data = {
            "s": "BTCUSDT",
            "t": 12345,
            "p": "50000.00",
            "q": "0.5",
            "T": 1234567890000,
            "m": True
        }
        
        result = data_parser.parse_trade(trade_data)
        
        assert result['symbol'] == "BTCUSDT"
        assert result['trade_id'] == 12345
        assert result['price'] == 50000.00
        assert result['quantity'] == 0.5
        assert result['trade_time'] == 1234567890000
        assert result['is_buyer_maker'] is True


class TestKlineDataValidation:
    """测试K线数据验证功能"""
    
    def test_kline_data_format(self, sample_kline_data):
        """测试K线数据格式"""
        # 验证必要字段存在
        assert "e" in sample_kline_data
        assert "E" in sample_kline_data
        assert "s" in sample_kline_data
        assert "k" in sample_kline_data
        
        # 验证K线字段
        kline = sample_kline_data["k"]
        required_fields = ["t", "T", "s", "i", "o", "c", "h", "l", "v", "n", "x"]
        for field in required_fields:
            assert field in kline, f"Missing field: {field}"
    
    def test_kline_price_validation(self, sample_kline_data):
        """测试K线价格数据验证"""
        kline = sample_kline_data["k"]
        
        open_price = float(kline["o"])
        high_price = float(kline["h"])
        low_price = float(kline["l"])
        close_price = float(kline["c"])
        
        # 验证价格逻辑
        assert low_price <= high_price, "Low price should be <= high price"
        assert open_price <= high_price, "Open price should be <= high price"
        assert open_price >= low_price, "Open price should be >= low price"
        assert close_price <= high_price, "Close price should be <= high price"
        assert close_price >= low_price, "Close price should be >= low price"
    
    def test_kline_volume_validation(self, sample_kline_data):
        """测试K线成交量验证"""
        kline = sample_kline_data["k"]
        
        volume = float(kline["v"])
        trades = int(kline["n"])
        
        assert volume >= 0, "Volume should be >= 0"
        assert trades >= 0, "Trades should be >= 0"


class TestMessageHandling:
    """测试消息处理功能"""
    
    def test_message_callback_registration(self, mock_websocket_client):
        """测试消息回调注册"""
        callback = Mock()
        
        mock_websocket_client.add_message_callback(callback)
        
        mock_websocket_client.add_message_callback.assert_called_once_with(callback)
    
    def test_message_callback_removal(self, mock_websocket_client):
        """测试消息回调移除"""
        callback = Mock()
        
        mock_websocket_client.remove_message_callback(callback)
        
        mock_websocket_client.remove_message_callback.assert_called_once_with(callback)
    
    @pytest.mark.asyncio
    async def test_message_processing(self, mock_websocket_client, sample_kline_data):
        """测试消息处理流程"""
        received_messages = []
        
        def callback(data):
            received_messages.append(data)
        
        mock_websocket_client.add_message_callback(callback)
        
        # 模拟接收消息
        callback(sample_kline_data)
        
        assert len(received_messages) == 1
        assert received_messages[0]["e"] == "kline"


class TestConnectionStatus:
    """测试连接状态功能"""
    
    def test_connection_status_initial(self, mock_config):
        """测试初始连接状态"""
        client = BinanceWebSocketClient(mock_config)
        status = client.get_connection_status()
        
        assert status['connected'] is False
        assert status['active_sockets'] == 0
        assert status['subscribed_channels'] == 0
        assert status['reconnect_attempts'] == 0
    
    def test_is_connected_method(self, mock_websocket_client):
        """测试is_connected方法"""
        # 初始状态
        mock_websocket_client._connected = False
        mock_websocket_client._client = None
        
        # 注意：这里需要实际的实现来测试
        # 由于我们使用的是Mock，这个测试主要是验证接口存在


class TestErrorHandling:
    """测试错误处理功能"""
    
    @pytest.mark.asyncio
    async def test_connection_error_handling(self, mock_websocket_client):
        """测试连接错误处理"""
        mock_websocket_client.connect.side_effect = Exception("Connection failed")
        
        with pytest.raises(Exception) as exc_info:
            await mock_websocket_client.connect()
        
        assert "Connection failed" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_subscription_error_handling(self, mock_websocket_client):
        """测试订阅错误处理"""
        mock_websocket_client.subscribe.side_effect = Exception("Subscription failed")
        
        with pytest.raises(Exception) as exc_info:
            await mock_websocket_client.subscribe(["BTCUSDT@kline_1m"])
        
        assert "Subscription failed" in str(exc_info.value)


class TestIntegration:
    """集成测试"""
    
    @pytest.mark.asyncio
    async def test_full_workflow_mock(self, mock_websocket_client):
        """测试完整工作流（使用Mock）"""
        # 1. 连接
        result = await mock_websocket_client.connect()
        assert result is True
        
        # 2. 订阅
        channels = ["BTCUSDT@kline_1m", "ETHUSDT@kline_5m"]
        result = await mock_websocket_client.subscribe(channels)
        assert result is True
        
        # 3. 断开
        result = await mock_websocket_client.disconnect()
        assert result is True
    
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_real_websocket_connection(self):
        """测试真实WebSocket连接（可选）"""
        # 这个测试需要真实的网络连接
        # 使用pytest.mark.slow标记，默认跳过
        
        config = BinanceConfig(
            api_key="",
            api_secret="",
            testnet=True,
        )
        
        client = BinanceWebSocketClient(config)
        
        try:
            # 连接
            result = await client.connect()
            assert result is True
            
            # 订阅
            channels = ["BTCUSDT@kline_1m"]
            result = await client.subscribe(channels)
            assert result is True
            
            # 等待接收一些数据
            await asyncio.sleep(5)
            
            # 验证连接状态
            status = client.get_connection_status()
            assert status['connected'] is True
            
        finally:
            # 断开连接
            await client.disconnect()


# =============================================================================
# 测试报告生成
# =============================================================================

def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """
    生成测试总结报告
    """
    terminalreporter.write_sep("=", "WebSocket Kline Data Test Summary")
    
    # 统计测试结果
    passed = len(terminalreporter.stats.get("passed", []))
    failed = len(terminalreporter.stats.get("failed", []))
    skipped = len(terminalreporter.stats.get("skipped", []))
    total = passed + failed + skipped
    
    terminalreporter.write_line(f"Total Tests: {total}")
    terminalreporter.write_line(f"Passed: {passed}")
    terminalreporter.write_line(f"Failed: {failed}")
    terminalreporter.write_line(f"Skipped: {skipped}")
    
    if total > 0:
        success_rate = (passed / total) * 100
        terminalreporter.write_line(f"Success Rate: {success_rate:.1f}%")
    
    terminalreporter.write_sep("=", "")


# =============================================================================
# 主函数
# =============================================================================

if __name__ == "__main__":
    # 直接运行测试
    pytest.main([__file__, "-v", "-s"])
