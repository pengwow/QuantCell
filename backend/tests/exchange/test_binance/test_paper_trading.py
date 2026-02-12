"""
Binance模拟盘交易测试
"""

import pytest
from exchange.binance.paper_trading import PaperTradingAccount, PaperOrder, PaperPosition
from exchange.binance.config import OrderSide, OrderType, OrderStatus, TimeInForce
from exchange.binance.exceptions import BinanceOrderError


class TestPaperTradingAccount:
    """测试模拟交易账户"""
    
    def setup_method(self):
        """每个测试方法前执行"""
        self.account = PaperTradingAccount(
            initial_balance={"USDT": 10000.0, "BTC": 0.5},
            maker_fee=0.001,
            taker_fee=0.001,
        )
        self.account.update_market_price("BTCUSDT", 50000.0)
    
    def test_initial_balance(self):
        """测试初始余额"""
        assert self.account.get_balance("USDT") == 10000.0
        assert self.account.get_balance("BTC") == 0.5
    
    def test_update_market_price(self):
        """测试更新市场价格"""
        self.account.update_market_price("ETHUSDT", 3000.0)
        assert self.account.market_prices["ETHUSDT"] == 3000.0
    
    def test_create_market_buy_order(self):
        """测试创建市价买单"""
        order = self.account.create_order(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.01,
        )
        
        assert order.symbol == "BTCUSDT"
        assert order.side == OrderSide.BUY
        assert order.order_type == OrderType.MARKET
        assert order.quantity == 0.01
        assert order.status == OrderStatus.FILLED
        assert order.filled_qty == 0.01
    
    def test_create_market_sell_order(self):
        """测试创建市价卖单"""
        order = self.account.create_order(
            symbol="BTCUSDT",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=0.01,
        )
        
        assert order.status == OrderStatus.FILLED
        assert order.filled_qty == 0.01
    
    def test_create_limit_order(self):
        """测试创建限价单"""
        # 买入限价单（限价高于市价，应该成交）
        order = self.account.create_order(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=0.01,
            price=51000.0,
        )
        
        assert order.status == OrderStatus.FILLED
        assert order.price == 51000.0
    
    def test_create_limit_order_not_filled(self):
        """测试未成交的限价单"""
        # 买入限价单（限价低于市价，不会成交）
        order = self.account.create_order(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=0.01,
            price=49000.0,
        )
        
        # 由于市价50000，限价49000，不会成交
        assert order.status == OrderStatus.NEW
    
    def test_insufficient_balance_buy(self):
        """测试买入余额不足"""
        with pytest.raises(BinanceOrderError):
            self.account.create_order(
                symbol="BTCUSDT",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=1.0,  # 需要50000 USDT，但只有10000
            )
    
    def test_insufficient_balance_sell(self):
        """测试卖出余额不足"""
        with pytest.raises(BinanceOrderError):
            self.account.create_order(
                symbol="BTCUSDT",
                side=OrderSide.SELL,
                order_type=OrderType.MARKET,
                quantity=1.0,  # 只有0.5 BTC
            )
    
    def test_limit_order_requires_price(self):
        """测试限价单需要价格"""
        with pytest.raises(BinanceOrderError):
            self.account.create_order(
                symbol="BTCUSDT",
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                quantity=0.01,
                price=None,
            )
    
    def test_cancel_order(self):
        """测试取消订单"""
        # 创建一个不会立即成交的限价单
        order = self.account.create_order(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=0.01,
            price=49000.0,
        )
        
        # 取消订单
        result = self.account.cancel_order(order.order_id)
        assert result is True
        assert order.status == OrderStatus.CANCELED
    
    def test_cancel_filled_order(self):
        """测试取消已成交订单"""
        order = self.account.create_order(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.01,
        )
        
        # 已成交的订单不能取消
        result = self.account.cancel_order(order.order_id)
        assert result is False
    
    def test_get_order(self):
        """测试获取订单"""
        order = self.account.create_order(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.01,
        )
        
        retrieved = self.account.get_order(order.order_id)
        assert retrieved == order
    
    def test_get_open_orders(self):
        """测试获取未成交订单"""
        # 创建一个市价单（已成交）
        market_order = self.account.create_order(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.01,
        )
        
        # 创建一个限价单（未成交）
        limit_order = self.account.create_order(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=0.01,
            price=49000.0,
        )
        
        open_orders = self.account.get_open_orders()
        assert len(open_orders) == 1
        assert open_orders[0].order_id == limit_order.order_id
    
    def test_position_update(self):
        """测试持仓更新"""
        # 买入创建多头持仓
        self.account.create_order(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.1,
        )
        
        position = self.account.get_position("BTCUSDT")
        assert position is not None
        assert position.side == "LONG"
        assert position.quantity == 0.1
    
    def test_position_close(self):
        """测试平仓"""
        # 先买入创建多头持仓
        self.account.create_order(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.1,
        )
        
        # 验证有多头持仓
        position = self.account.get_position("BTCUSDT")
        assert position is not None
        assert position.side == "LONG"
        
        # 卖出平仓
        self.account.create_order(
            symbol="BTCUSDT",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=0.1,
        )
        
        # 持仓应该被删除
        position = self.account.get_position("BTCUSDT")
        assert position is None
    
    def test_account_summary(self):
        """测试账户摘要"""
        summary = self.account.get_account_summary()
        
        assert "balances" in summary
        assert "total_balance" in summary
        assert "position_value" in summary
        assert "unrealized_pnl" in summary
        assert "total_equity" in summary
    
    def test_fee_calculation(self):
        """测试手续费计算"""
        initial_usdt = self.account.get_balance("USDT")
        
        order = self.account.create_order(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.01,
        )
        
        # 检查手续费
        cost = 0.01 * 50000.0
        fee = cost * 0.001  # taker_fee
        expected_balance = initial_usdt - cost - fee
        
        assert self.account.get_balance("USDT") == pytest.approx(expected_balance, 0.01)


class TestPaperOrder:
    """测试模拟订单"""
    
    def test_order_creation(self):
        """测试订单创建"""
        order = PaperOrder(
            order_id="test-id",
            client_order_id="client-id",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=0.01,
            price=50000.0,
            time_in_force=TimeInForce.GTC,
            status=OrderStatus.NEW,
        )
        
        assert order.order_id == "test-id"
        assert order.remaining_qty == 0.01
        assert not order.is_filled


class TestPaperPosition:
    """测试模拟持仓"""
    
    def test_position_pnl(self):
        """测试持仓盈亏计算"""
        position = PaperPosition(
            symbol="BTCUSDT",
            quantity=0.1,
            avg_price=50000.0,
            side="LONG",
        )
        
        # 价格上涨
        position.update_unrealized_pnl(55000.0)
        assert position.unrealized_pnl == 500.0  # (55000 - 50000) * 0.1
        
        # 价格下跌
        position.update_unrealized_pnl(45000.0)
        assert position.unrealized_pnl == -500.0
    
    def test_short_position_pnl(self):
        """测试空头持仓盈亏"""
        position = PaperPosition(
            symbol="BTCUSDT",
            quantity=0.1,
            avg_price=50000.0,
            side="SHORT",
        )
        
        # 价格上涨，空头亏损
        position.update_unrealized_pnl(55000.0)
        assert position.unrealized_pnl == -500.0
        
        # 价格下跌，空头盈利
        position.update_unrealized_pnl(45000.0)
        assert position.unrealized_pnl == 500.0
