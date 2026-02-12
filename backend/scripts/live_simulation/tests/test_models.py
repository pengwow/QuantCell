"""
数据模型测试
"""

from datetime import datetime

import pytest

from ..models import (
    KlineData,
    MarketDataMessage,
    TradeSignal,
    SignalType,
    OrderInfo,
    OrderSide,
    OrderType,
    OrderStatus,
    PositionInfo,
    WorkerStatus,
    WorkerState,
)


class TestKlineData:
    """测试K线数据模型"""
    
    def test_create_kline(self):
        """测试创建K线数据"""
        kline = KlineData(
            symbol="BTCUSDT",
            timestamp=datetime.now(),
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=1000.0,
            interval="1m",
        )
        
        assert kline.symbol == "BTCUSDT"
        assert kline.open == 100.0
        assert kline.interval == "1m"
    
    def test_to_dict(self):
        """测试转换为字典"""
        kline = KlineData(
            symbol="BTCUSDT",
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=1000.0,
        )
        
        data = kline.to_dict()
        
        assert data["symbol"] == "BTCUSDT"
        assert data["open"] == 100.0
        assert "timestamp" in data
    
    def test_from_dict(self):
        """测试从字典创建"""
        data = {
            "symbol": "BTCUSDT",
            "timestamp": "2024-01-01T12:00:00",
            "open": "100.0",
            "high": "101.0",
            "low": "99.0",
            "close": "100.5",
            "volume": "1000.0",
            "interval": "1m",
        }
        
        kline = KlineData.from_dict(data)
        
        assert kline.symbol == "BTCUSDT"
        assert kline.open == 100.0
        assert kline.interval == "1m"


class TestTradeSignal:
    """测试交易信号模型"""
    
    def test_create_signal(self):
        """测试创建交易信号"""
        signal = TradeSignal(
            symbol="BTCUSDT",
            signal_type=SignalType.BUY,
            strength=0.8,
            timestamp=datetime.now(),
            price=100.0,
            volume=1.0,
            strategy_id="TestStrategy",
        )
        
        assert signal.symbol == "BTCUSDT"
        assert signal.signal_type == SignalType.BUY
        assert signal.strength == 0.8
    
    def test_signal_strength_validation(self):
        """测试信号强度验证"""
        with pytest.raises(ValueError):
            TradeSignal(
                symbol="BTCUSDT",
                signal_type=SignalType.BUY,
                strength=1.5,  # 超出范围
                timestamp=datetime.now(),
                price=100.0,
                volume=1.0,
                strategy_id="TestStrategy",
            )


class TestOrderInfo:
    """测试订单信息模型"""
    
    def test_create_order(self):
        """测试创建订单"""
        order = OrderInfo(
            order_id="test_order_1",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=1.0,
            price=100.0,
        )
        
        assert order.order_id == "test_order_1"
        assert order.symbol == "BTCUSDT"
        assert order.side == OrderSide.BUY
        assert order.status == OrderStatus.PENDING
    
    def test_auto_generate_order_id(self):
        """测试自动生成订单ID"""
        order = OrderInfo(
            order_id="",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=1.0,
        )
        
        assert order.order_id != ""
        assert len(order.order_id) > 0


class TestPositionInfo:
    """测试持仓信息模型"""
    
    def test_create_position(self):
        """测试创建持仓"""
        position = PositionInfo(
            symbol="BTCUSDT",
            quantity=1.0,
            avg_price=100.0,
            current_price=105.0,
        )
        
        assert position.symbol == "BTCUSDT"
        assert position.quantity == 1.0
        assert position.unrealized_pnl == 5.0  # (105 - 100) * 1
    
    def test_update_price(self):
        """测试更新价格"""
        position = PositionInfo(
            symbol="BTCUSDT",
            quantity=2.0,
            avg_price=100.0,
            current_price=100.0,
        )
        
        position.update_price(110.0)
        
        assert position.current_price == 110.0
        assert position.unrealized_pnl == 20.0  # (110 - 100) * 2


class TestWorkerStatus:
    """测试Worker状态模型"""
    
    def test_create_worker_status(self):
        """测试创建Worker状态"""
        status = WorkerStatus(
            worker_id="worker_1",
            state=WorkerState.RUNNING,
            strategy_name="TestStrategy",
        )
        
        assert status.worker_id == "worker_1"
        assert status.state == WorkerState.RUNNING
        assert status.strategy_name == "TestStrategy"
    
    def test_update_heartbeat(self):
        """测试更新心跳"""
        status = WorkerStatus(worker_id="worker_1")
        
        assert status.last_heartbeat is None
        
        status.update_heartbeat()
        
        assert status.last_heartbeat is not None
