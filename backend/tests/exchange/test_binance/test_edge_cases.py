"""
Binance模块边界条件测试

测试极端值、异常情况和边界条件
"""

import pytest
import sys
from decimal import Decimal
from exchange.binance.paper_trading import PaperTradingAccount
from exchange.binance.config import OrderSide, OrderType, OrderStatus, TimeInForce
from exchange.binance.exceptions import BinanceOrderError


class TestEdgeCases:
    """边界条件测试"""
    
    def setup_method(self):
        """每个测试方法前执行"""
        self.account = PaperTradingAccount(
            initial_balance={"USDT": 10000.0, "BTC": 0.5},
            maker_fee=0.001,
            taker_fee=0.001,
        )
        self.account.update_market_price("BTCUSDT", 50000.0)
    
    # ==================== 零值测试 ====================
    
    def test_zero_quantity(self):
        """测试数量为0"""
        with pytest.raises(BinanceOrderError):
            self.account.create_order(
                symbol="BTCUSDT",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=0,
            )
    
    def test_zero_price_limit_order(self):
        """测试限价单价格为0"""
        with pytest.raises(BinanceOrderError):
            self.account.create_order(
                symbol="BTCUSDT",
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                quantity=0.01,
                price=0,
            )
    
    # ==================== 负值测试 ====================
    
    def test_negative_quantity(self):
        """测试负数数量"""
        with pytest.raises(BinanceOrderError):
            self.account.create_order(
                symbol="BTCUSDT",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=-0.01,
            )
    
    def test_negative_price(self):
        """测试负数价格"""
        with pytest.raises(BinanceOrderError):
            self.account.create_order(
                symbol="BTCUSDT",
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                quantity=0.01,
                price=-50000,
            )
    
    # ==================== 极大值测试 ====================
    
    def test_very_large_quantity(self):
        """测试超大数量"""
        # 数量超过余额
        with pytest.raises(BinanceOrderError):
            self.account.create_order(
                symbol="BTCUSDT",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=1e10,  # 100亿个BTC
            )
    
    def test_very_large_price(self):
        """测试超大价格"""
        # 价格极大，超过余额
        with pytest.raises(BinanceOrderError):
            self.account.create_order(
                symbol="BTCUSDT",
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                quantity=0.01,
                price=1e12,  # 1万亿美元
            )
    
    # ==================== 极小值测试 ====================
    
    def test_very_small_quantity(self):
        """测试极小数量"""
        # 极小的数量应该可以创建订单
        order = self.account.create_order(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=1e-8,  # 0.00000001 BTC
        )
        assert order.status == OrderStatus.FILLED
    
    def test_very_small_price(self):
        """测试极小价格"""
        # 极低的价格
        order = self.account.create_order(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=0.01,
            price=1e-8,  # 极低价格
        )
        # 由于价格低于市价，不会成交
        assert order.status == OrderStatus.NEW
    
    # ==================== 空值测试 ====================
    
    def test_empty_symbol(self):
        """测试空交易对"""
        with pytest.raises((BinanceOrderError, AttributeError)):
            self.account.create_order(
                symbol="",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=0.01,
            )
    
    def test_none_symbol(self):
        """测试None交易对"""
        with pytest.raises((BinanceOrderError, AttributeError)):
            self.account.create_order(
                symbol=None,
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=0.01,
            )
    
    # ==================== 精度测试 ====================
    
    def test_high_precision_price(self):
        """测试高精度价格"""
        # 8位小数精度
        order = self.account.create_order(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=0.01,
            price=50000.12345678,
        )
        assert order.price == 50000.12345678
    
    def test_high_precision_quantity(self):
        """测试高精度数量"""
        # 8位小数精度
        order = self.account.create_order(
            symbol="BTCUSDT",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=0.12345678,
        )
        assert order.quantity == 0.12345678
    
    # ==================== 余额边界测试 ====================
    
    def test_exact_balance_buy(self):
        """测试刚好足够的余额买入"""
        # 计算刚好足够的数量
        price = 50000.0
        available_usdt = 10000.0
        # 考虑手续费，实际可用的金额
        quantity = available_usdt / price / 1.001  # 考虑0.1%手续费
        
        order = self.account.create_order(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=quantity,
        )
        assert order.status == OrderStatus.FILLED
    
    def test_exact_balance_sell(self):
        """测试刚好足够的余额卖出"""
        # 卖出全部BTC
        order = self.account.create_order(
            symbol="BTCUSDT",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=0.5,  # 全部BTC
        )
        assert order.status == OrderStatus.FILLED
        assert self.account.get_balance("BTC") == 0
    
    def test_just_insufficient_balance_buy(self):
        """测试刚好不足的余额买入"""
        # 稍微超过余额
        with pytest.raises(BinanceOrderError):
            self.account.create_order(
                symbol="BTCUSDT",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=0.2001,  # 需要10000.5 USDT，但只有10000
            )
    
    def test_just_insufficient_balance_sell(self):
        """测试刚好不足的余额卖出"""
        with pytest.raises(BinanceOrderError):
            self.account.create_order(
                symbol="BTCUSDT",
                side=OrderSide.SELL,
                order_type=OrderType.MARKET,
                quantity=0.5000001,  # 稍微超过0.5 BTC
            )
    
    # ==================== 特殊交易对测试 ====================
    
    def test_various_trading_pairs(self):
        """测试不同格式的交易对"""
        test_cases = [
            ("BTCUSDT", 50000.0),
            ("ETHBTC", 0.065),
            ("ADAUSDT", 1.5),
            ("XRPUSDT", 0.5),
        ]
        
        for symbol, price in test_cases:
            self.account.update_market_price(symbol, price)
            order = self.account.create_order(
                symbol=symbol,
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                quantity=0.01,
                price=price * 1.1,  # 高于市价确保成交
            )
            assert order.symbol == symbol.upper()
    
    # ==================== 订单状态边界测试 ====================
    
    def test_cancel_nonexistent_order(self):
        """测试取消不存在的订单"""
        result = self.account.cancel_order("nonexistent-order-id")
        assert result is False
    
    def test_get_nonexistent_order(self):
        """测试获取不存在的订单"""
        order = self.account.get_order("nonexistent-order-id")
        assert order is None
    
    def test_double_cancel_order(self):
        """测试重复取消订单"""
        # 创建未成交订单
        order = self.account.create_order(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=0.01,
            price=1000.0,  # 远低于市价，不会成交
        )
        
        # 第一次取消
        result1 = self.account.cancel_order(order.order_id)
        assert result1 is True
        
        # 第二次取消（已取消的订单）
        result2 = self.account.cancel_order(order.order_id)
        assert result2 is False
    
    # ==================== 持仓边界测试 ====================
    
    def test_position_with_zero_quantity(self):
        """测试持仓数量归零"""
        # 先买入
        self.account.create_order(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.1,
        )
        
        # 再卖出相同数量
        self.account.create_order(
            symbol="BTCUSDT",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=0.1,
        )
        
        # 持仓应该被删除
        position = self.account.get_position("BTCUSDT")
        assert position is None
    
    def test_multiple_positions(self):
        """测试多个持仓"""
        symbols = ["BTCUSDT", "ETHUSDT", "ADAUSDT"]
        
        for symbol in symbols:
            self.account.update_market_price(symbol, 100.0)
            self.account.create_order(
                symbol=symbol,
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=0.01,
            )
        
        positions = self.account.get_all_positions()
        assert len(positions) == 3
    
    # ==================== 手续费边界测试 ====================
    
    def test_zero_fee(self):
        """测试零手续费"""
        account = PaperTradingAccount(
            initial_balance={"USDT": 10000.0},
            maker_fee=0.0,
            taker_fee=0.0,
        )
        account.update_market_price("BTCUSDT", 50000.0)
        
        initial_usdt = account.get_balance("USDT")
        
        order = account.create_order(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.1,
        )
        
        # 无手续费，余额应该精确减少
        cost = 0.1 * 50000.0
        expected_balance = initial_usdt - cost
        assert account.get_balance("USDT") == expected_balance
    
    def test_very_high_fee(self):
        """测试极高手续费"""
        account = PaperTradingAccount(
            initial_balance={"USDT": 10000.0},
            maker_fee=0.5,  # 50%手续费
            taker_fee=0.5,
        )
        account.update_market_price("BTCUSDT", 50000.0)
        
        initial_usdt = account.get_balance("USDT")
        
        order = account.create_order(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.1,
        )
        
        # 50%手续费
        cost = 0.1 * 50000.0
        fee = cost * 0.5
        expected_balance = initial_usdt - cost - fee
        assert account.get_balance("USDT") == expected_balance
    
    # ==================== 并发边界测试 ====================
    
    def test_rapid_order_creation(self):
        """测试快速创建多个订单"""
        orders = []
        for i in range(100):
            order = self.account.create_order(
                symbol="BTCUSDT",
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                quantity=0.001,
                price=1000.0 + i,  # 不同的价格
            )
            orders.append(order)
        
        # 验证所有订单都创建了
        assert len(orders) == 100
        assert len(self.account.orders) == 100
    
    # ==================== 浮点数精度测试 ====================
    
    def test_floating_point_precision(self):
        """测试浮点数精度问题"""
        # 使用可能导致精度问题的值
        self.account.update_market_price("BTCUSDT", 0.1)
        
        order = self.account.create_order(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.1,
        )
        
        # 验证计算正确
        cost = 0.1 * 0.1  # 0.01
        fee = cost * 0.001  # 0.00001
        expected_balance = 10000.0 - cost - fee
        
        assert abs(self.account.get_balance("USDT") - expected_balance) < 1e-10
