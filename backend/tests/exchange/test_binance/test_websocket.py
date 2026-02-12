"""
Binance WebSocket功能测试

测试WebSocket连接和数据接收功能
"""

import pytest
import asyncio
import os
from exchange.binance import BinanceWebSocketManager, BinanceConfig
from exchange.binance.exceptions import BinanceWebSocketError


# 标记需要API密钥的测试
requires_api_key = pytest.mark.skipif(
    not os.getenv("BINANCE_TESTNET_API_KEY"),
    reason="需要设置BINANCE_TESTNET_API_KEY环境变量"
)


class TestWebSocket:
    """WebSocket功能测试"""
    
    @pytest.fixture
    async def ws_manager(self):
        """创建WebSocket管理器"""
        api_key = os.getenv("BINANCE_TESTNET_API_KEY")
        api_secret = os.getenv("BINANCE_TESTNET_API_SECRET")
        
        config = BinanceConfig(
            api_key=api_key,
            api_secret=api_secret,
            testnet=True,
        )
        
        manager = BinanceWebSocketManager(config)
        yield manager
        
        # 清理
        if manager.is_connected:
            await manager.disconnect()
    
    # ==================== 连接测试 ====================
    
    @requires_api_key
    @pytest.mark.asyncio
    async def test_connect_success(self, ws_manager):
        """测试成功连接"""
        result = await ws_manager.connect()
        assert result is True
        assert ws_manager.is_connected is True
    
    @pytest.mark.asyncio
    async def test_connect_without_credentials(self):
        """测试无凭证连接"""
        config = BinanceConfig(testnet=True)
        manager = BinanceWebSocketManager(config)
        
        try:
            result = await manager.connect()
            assert result is True
            assert manager.is_connected is True
        finally:
            await manager.disconnect()
    
    @pytest.mark.asyncio
    async def test_disconnect_without_connect(self):
        """测试未连接时断开"""
        config = BinanceConfig(testnet=True)
        manager = BinanceWebSocketManager(config)
        
        # 应该可以安全调用
        await manager.disconnect()
    
    # ==================== K线订阅测试 ====================
    
    @requires_api_key
    @pytest.mark.asyncio
    async def test_subscribe_kline(self, ws_manager):
        """测试订阅K线数据"""
        await ws_manager.connect()
        
        messages = []
        
        def on_kline(data):
            messages.append(data)
        
        ws_manager.register_callback("kline", on_kline)
        
        # 订阅K线
        sub_id = await ws_manager.subscribe_kline("BTCUSDT", "1m")
        assert sub_id is not None
        
        # 等待接收数据（最多5秒）
        await asyncio.wait_for(
            self._wait_for_messages(messages, 1),
            timeout=10.0
        )
        
        assert len(messages) >= 1
        
        # 验证数据结构
        msg = messages[0]
        assert msg["type"] == "kline"
        assert "symbol" in msg
        assert "open" in msg
        assert "high" in msg
        assert "low" in msg
        assert "close" in msg
    
    # ==================== 深度订阅测试 ====================
    
    @requires_api_key
    @pytest.mark.asyncio
    async def test_subscribe_depth(self, ws_manager):
        """测试订阅深度数据"""
        await ws_manager.connect()
        
        messages = []
        
        def on_depth(data):
            messages.append(data)
        
        ws_manager.register_callback("depth", on_depth)
        
        # 订阅深度
        sub_id = await ws_manager.subscribe_depth("BTCUSDT", "20")
        assert sub_id is not None
        
        # 等待接收数据
        await asyncio.wait_for(
            self._wait_for_messages(messages, 1),
            timeout=10.0
        )
        
        assert len(messages) >= 1
        
        # 验证数据结构
        msg = messages[0]
        assert msg["type"] == "depth"
        assert "bids" in msg
        assert "asks" in msg
        assert isinstance(msg["bids"], list)
        assert isinstance(msg["asks"], list)
    
    # ==================== 交易订阅测试 ====================
    
    @requires_api_key
    @pytest.mark.asyncio
    async def test_subscribe_trade(self, ws_manager):
        """测试订阅交易数据"""
        await ws_manager.connect()
        
        messages = []
        
        def on_trade(data):
            messages.append(data)
        
        ws_manager.register_callback("trade", on_trade)
        
        # 订阅交易
        sub_id = await ws_manager.subscribe_trade("BTCUSDT")
        assert sub_id is not None
        
        # 等待接收数据
        await asyncio.wait_for(
            self._wait_for_messages(messages, 1),
            timeout=10.0
        )
        
        assert len(messages) >= 1
        
        # 验证数据结构
        msg = messages[0]
        assert msg["type"] == "trade"
        assert "price" in msg
        assert "quantity" in msg
    
    # ==================== Ticker订阅测试 ====================
    
    @requires_api_key
    @pytest.mark.asyncio
    async def test_subscribe_ticker(self, ws_manager):
        """测试订阅Ticker数据"""
        await ws_manager.connect()
        
        messages = []
        
        def on_ticker(data):
            messages.append(data)
        
        ws_manager.register_callback("ticker", on_ticker)
        
        # 订阅Ticker
        sub_id = await ws_manager.subscribe_ticker("BTCUSDT")
        assert sub_id is not None
        
        # 等待接收数据
        await asyncio.wait_for(
            self._wait_for_messages(messages, 1),
            timeout=10.0
        )
        
        assert len(messages) >= 1
        
        # 验证数据结构
        msg = messages[0]
        assert msg["type"] == "ticker"
        assert "last_price" in msg
        assert "volume" in msg
    
    # ==================== 多订阅测试 ====================
    
    @requires_api_key
    @pytest.mark.asyncio
    async def test_multiple_subscriptions(self, ws_manager):
        """测试多个订阅"""
        await ws_manager.connect()
        
        kline_messages = []
        trade_messages = []
        
        def on_kline(data):
            kline_messages.append(data)
        
        def on_trade(data):
            trade_messages.append(data)
        
        ws_manager.register_callback("kline", on_kline)
        ws_manager.register_callback("trade", on_trade)
        
        # 订阅多个数据流
        sub1 = await ws_manager.subscribe_kline("BTCUSDT", "1m")
        sub2 = await ws_manager.subscribe_trade("BTCUSDT")
        
        assert sub1 != sub2
        
        # 等待接收数据
        await asyncio.wait_for(
            self._wait_for_messages(kline_messages, 1),
            timeout=10.0
        )
        
        await asyncio.wait_for(
            self._wait_for_messages(trade_messages, 1),
            timeout=10.0
        )
        
        assert len(kline_messages) >= 1
        assert len(trade_messages) >= 1
    
    # ==================== 取消订阅测试 ====================
    
    @requires_api_key
    @pytest.mark.asyncio
    async def test_unsubscribe(self, ws_manager):
        """测试取消订阅"""
        await ws_manager.connect()
        
        # 订阅
        sub_id = await ws_manager.subscribe_kline("BTCUSDT", "1m")
        
        # 取消订阅
        await ws_manager.unsubscribe(sub_id)
        
        # 验证订阅已移除
        assert sub_id not in ws_manager._active_sockets
    
    # ==================== 回调测试 ====================
    
    @requires_api_key
    @pytest.mark.asyncio
    async def test_register_unregister_callback(self, ws_manager):
        """测试注册和注销回调"""
        messages = []
        
        def callback(data):
            messages.append(data)
        
        # 注册回调
        ws_manager.register_callback("kline", callback)
        assert callback in ws_manager._callbacks["kline"]
        
        # 注销回调
        ws_manager.unregister_callback("kline", callback)
        assert callback not in ws_manager._callbacks["kline"]
    
    @requires_api_key
    @pytest.mark.asyncio
    async def test_async_callback(self, ws_manager):
        """测试异步回调"""
        await ws_manager.connect()
        
        messages = []
        
        async def async_callback(data):
            await asyncio.sleep(0.001)  # 模拟异步操作
            messages.append(data)
        
        ws_manager.register_callback("kline", async_callback)
        
        # 订阅
        await ws_manager.subscribe_kline("BTCUSDT", "1m")
        
        # 等待接收数据
        await asyncio.wait_for(
            self._wait_for_messages(messages, 1),
            timeout=10.0
        )
        
        assert len(messages) >= 1
    
    # ==================== 统计信息测试 ====================
    
    @requires_api_key
    @pytest.mark.asyncio
    async def test_websocket_stats(self, ws_manager):
        """测试WebSocket统计信息"""
        await ws_manager.connect()
        
        # 订阅并接收一些数据
        ws_manager.register_callback("kline", lambda x: None)
        await ws_manager.subscribe_kline("BTCUSDT", "1m")
        
        # 等待接收数据
        await asyncio.sleep(2)
        
        stats = ws_manager.stats
        
        assert stats.connected_at is not None
        assert stats.messages_received > 0
        assert stats.connection_duration > 0
    
    # ==================== 错误处理测试 ====================
    
    @pytest.mark.asyncio
    async def test_invalid_symbol(self):
        """测试无效交易对 - Binance WebSocket不会立即报错，但会静默失败"""
        config = BinanceConfig(testnet=True)
        manager = BinanceWebSocketManager(config)
        
        try:
            await manager.connect()
            
            # 订阅无效交易对 - 不会抛出异常，但也不会收到数据
            sub_id = await manager.subscribe_kline("INVALID_SYMBOL", "1m")
            assert sub_id is not None
            
            # 验证订阅已创建
            assert sub_id in manager._active_sockets
        finally:
            await manager.disconnect()
    
    @pytest.mark.asyncio
    async def test_subscribe_without_connect(self):
        """测试未连接时订阅"""
        config = BinanceConfig(testnet=True)
        manager = BinanceWebSocketManager(config)
        
        with pytest.raises(BinanceWebSocketError):
            await manager.subscribe_kline("BTCUSDT", "1m")
    
    # ==================== 辅助方法 ====================
    
    async def _wait_for_messages(self, messages_list, min_count, timeout=5.0):
        """等待接收消息"""
        start_time = asyncio.get_event_loop().time()
        
        while len(messages_list) < min_count:
            if asyncio.get_event_loop().time() - start_time > timeout:
                break
            await asyncio.sleep(0.1)
        
        return len(messages_list) >= min_count
