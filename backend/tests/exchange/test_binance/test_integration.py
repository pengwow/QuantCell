"""
Binance模块集成测试

使用Binance测试网进行真实API测试
注意：这些测试需要有效的测试网API密钥
"""

import pytest
import os
from exchange.binance import BinanceClient, BinanceConfig
from exchange.binance.config import OrderSide, OrderType, OrderRequest, TimeInForce
from exchange.binance.exceptions import (
    BinanceConnectionError,
    BinanceAPIError,
    BinanceAuthenticationError,
)

# 标记需要API密钥的测试
requires_api_key = pytest.mark.skipif(
    not os.getenv("BINANCE_TESTNET_API_KEY"),
    reason="需要设置BINANCE_TESTNET_API_KEY环境变量"
)


class TestIntegration:
    """集成测试"""
    
    @pytest.fixture
    def client(self):
        """创建测试客户端"""
        api_key = os.getenv("BINANCE_TESTNET_API_KEY")
        api_secret = os.getenv("BINANCE_TESTNET_API_SECRET")
        
        config = BinanceConfig(
            api_key=api_key,
            api_secret=api_secret,
            testnet=True,
        )
        
        client = BinanceClient(config)
        yield client
        
        # 清理
        if client.is_connected:
            client.disconnect()
    
    # ==================== 连接测试 ====================
    
    @requires_api_key
    def test_connect_success(self, client):
        """测试成功连接"""
        result = client.connect()
        assert result is True
        assert client.is_connected is True
    
    def test_connect_without_credentials(self):
        """测试无凭证连接"""
        config = BinanceConfig(testnet=True)
        client = BinanceClient(config)
        
        # 无凭证时应该抛出异常
        with pytest.raises(BinanceConnectionError):
            client.connect()
    
    def test_connect_invalid_credentials(self):
        """测试无效凭证连接"""
        config = BinanceConfig(
            api_key="invalid_key",
            api_secret="invalid_secret",
            testnet=True,
        )
        client = BinanceClient(config)
        
        # 连接应该失败或认证失败
        with pytest.raises((BinanceConnectionError, BinanceAuthenticationError)):
            client.connect()
    
    # ==================== 市场数据测试 ====================
    
    @requires_api_key
    def test_get_ticker(self, client):
        """测试获取ticker"""
        client.connect()
        
        ticker = client.get_ticker("BTCUSDT")
        
        assert ticker.symbol == "BTCUSDT"
        assert ticker.price > 0
        assert ticker.timestamp > 0
    
    @requires_api_key
    def test_get_klines(self, client):
        """测试获取K线"""
        client.connect()
        
        klines = client.get_klines("BTCUSDT", "1h", limit=10)
        
        assert len(klines) <= 10
        assert len(klines) > 0
        
        # 验证K线数据结构
        kline = klines[0]
        assert "open" in kline
        assert "high" in kline
        assert "low" in kline
        assert "close" in kline
        assert "volume" in kline
    
    @requires_api_key
    def test_get_order_book(self, client):
        """测试获取订单簿"""
        client.connect()
        
        depth = client.get_order_book("BTCUSDT", limit=10)
        
        assert "bids" in depth
        assert "asks" in depth
        assert len(depth["bids"]) <= 10
        assert len(depth["asks"]) <= 10
    
    @requires_api_key
    def test_get_recent_trades(self, client):
        """测试获取最近成交"""
        client.connect()
        
        trades = client.get_recent_trades("BTCUSDT", limit=10)
        
        assert len(trades) <= 10
        
        if trades:
            trade = trades[0]
            assert "price" in trade
            assert "qty" in trade
            assert "time" in trade
    
    # ==================== 账户测试 ====================
    
    @requires_api_key
    def test_get_account(self, client):
        """测试获取账户信息"""
        client.connect()
        
        account = client.get_account()
        
        assert "balances" in account
        assert len(account["balances"]) > 0
    
    @requires_api_key
    def test_get_balance(self, client):
        """测试获取余额"""
        client.connect()
        
        balances = client.get_balance()
        
        assert isinstance(balances, list)
        
        # 应该包含USDT
        usdt_balance = next(
            (b for b in balances if b.asset == "USDT"),
            None
        )
        # 测试网账户可能没有USDT
    
    @requires_api_key
    def test_get_specific_balance(self, client):
        """测试获取特定资产余额"""
        client.connect()
        
        balances = client.get_balance("BTC")
        
        assert isinstance(balances, list)
        if balances:
            assert balances[0].asset == "BTC"
    
    # ==================== 订单测试 ====================
    
    @requires_api_key
    def test_create_limit_order(self, client):
        """测试创建限价单"""
        client.connect()
        
        # 获取当前价格
        ticker = client.get_ticker("BTCUSDT")
        current_price = ticker.price
        
        # 创建一个远低于市价的买单（不会成交）
        order_request = OrderRequest(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=0.001,
            price=current_price * 0.5,  # 50%的当前价格
            time_in_force=TimeInForce.GTC,
        )
        
        response = client.create_order(order_request)
        
        assert response.symbol == "BTCUSDT"
        assert response.side == OrderSide.BUY
        assert response.order_type == OrderType.LIMIT
        assert response.status.value in ["NEW", "PARTIALLY_FILLED", "FILLED"]
        
        # 清理：取消订单
        try:
            client.cancel_order("BTCUSDT", response.order_id)
        except:
            pass
    
    @requires_api_key
    def test_get_open_orders(self, client):
        """测试获取未成交订单"""
        client.connect()
        
        orders = client.get_open_orders("BTCUSDT")
        
        assert isinstance(orders, list)
    
    @requires_api_key
    def test_get_all_orders(self, client):
        """测试获取所有订单"""
        client.connect()
        
        orders = client.get_all_orders("BTCUSDT", limit=10)
        
        assert isinstance(orders, list)
        assert len(orders) <= 10
    
    # ==================== 错误场景测试 ====================
    
    @requires_api_key
    def test_invalid_symbol(self, client):
        """测试无效交易对"""
        client.connect()
        
        with pytest.raises(BinanceAPIError):
            client.get_ticker("INVALID_SYMBOL")
    
    @requires_api_key
    def test_invalid_interval(self, client):
        """测试无效时间间隔"""
        client.connect()
        
        with pytest.raises(BinanceAPIError):
            client.get_klines("BTCUSDT", "invalid_interval")
    
    def test_disconnect_without_connect(self):
        """测试未连接时断开"""
        config = BinanceConfig(testnet=True)
        client = BinanceClient(config)
        
        # 应该可以安全调用
        client.disconnect()
    
    # ==================== 异步测试 ====================
    
    @requires_api_key
    @pytest.mark.asyncio
    async def test_async_connect(self):
        """测试异步连接"""
        api_key = os.getenv("BINANCE_TESTNET_API_KEY")
        api_secret = os.getenv("BINANCE_TESTNET_API_SECRET")
        
        config = BinanceConfig(
            api_key=api_key,
            api_secret=api_secret,
            testnet=True,
        )
        
        client = BinanceClient(config)
        
        try:
            result = await client.connect_async()
            assert result is True
            assert client.is_connected is True
        finally:
            await client.disconnect_async()
    
    @requires_api_key
    @pytest.mark.asyncio
    async def test_async_get_ticker(self):
        """测试异步获取ticker"""
        api_key = os.getenv("BINANCE_TESTNET_API_KEY")
        api_secret = os.getenv("BINANCE_TESTNET_API_SECRET")
        
        config = BinanceConfig(
            api_key=api_key,
            api_secret=api_secret,
            testnet=True,
        )
        
        client = BinanceClient(config)
        
        try:
            await client.connect_async()
            ticker = client.get_ticker("BTCUSDT")
            assert ticker.price > 0
        finally:
            await client.disconnect_async()
