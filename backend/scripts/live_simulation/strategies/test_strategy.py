"""
测试策略示例

这是一个简单的测试策略，用于验证模拟测试系统。
"""

from typing import Any, Dict, List
from datetime import datetime
from enum import Enum


class SignalType(str, Enum):
    """信号类型枚举"""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


class TradeSignal:
    """交易信号"""
    def __init__(
        self,
        symbol: str,
        signal_type: SignalType,
        strength: float,
        timestamp: datetime,
        price: float,
        volume: float,
        strategy_id: str,
        params: Dict[str, Any] = None
    ):
        self.symbol = symbol
        self.signal_type = signal_type
        self.strength = strength
        self.timestamp = timestamp
        self.price = price
        self.volume = volume
        self.strategy_id = strategy_id
        self.params = params or {}


class OrderSide(str, Enum):
    """订单方向枚举"""
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    """订单类型枚举"""
    MARKET = "market"
    LIMIT = "limit"


class OrderInfo:
    """订单信息"""
    def __init__(
        self,
        order_id: str,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: float,
        price: float = None
    ):
        self.order_id = order_id
        self.symbol = symbol
        self.side = side
        self.order_type = order_type
        self.quantity = quantity
        self.price = price


class TestStrategy:
    """测试策略"""
    
    def __init__(self, params: Dict[str, Any] = None):
        self.params = params or {}
        self.name = "TestStrategy"
        self.version = "1.0.0"
        
        # 策略参数
        self.fast_period = self.params.get("fast_period", 5)
        self.slow_period = self.params.get("slow_period", 10)
        
        # 状态
        self.initialized = False
        self.data_history: List[Dict[str, Any]] = []
        self.signals: List[TradeSignal] = []
        self.orders: List[OrderInfo] = []
        
    def initialize(self):
        """初始化策略"""
        self.initialized = True
        print(f"Strategy {self.name} initialized")
        
    def on_data(self, data: Dict[str, Any]) -> List[TradeSignal]:
        """
        处理市场数据
        
        Args:
            data: 市场数据字典
            
        Returns:
            交易信号列表
        """
        if not self.initialized:
            self.initialize()
            
        # 保存数据历史
        self.data_history.append(data)
        
        # 保持历史数据长度
        max_history = max(self.fast_period, self.slow_period) + 10
        if len(self.data_history) > max_history:
            self.data_history.pop(0)
            
        # 生成信号（简单的均线交叉策略）
        signals = self._generate_signals(data)
        
        return signals
        
    def _generate_signals(self, data: Dict[str, Any]) -> List[TradeSignal]:
        """生成交易信号"""
        signals = []
        
        if len(self.data_history) < self.slow_period:
            return signals
            
        # 计算均线
        closes = [d.get("close", 0) for d in self.data_history[-self.slow_period:]]
        fast_ma = sum(closes[-self.fast_period:]) / self.fast_period
        slow_ma = sum(closes) / self.slow_period
        
        # 获取当前价格
        current_price = data.get("close", 0)
        symbol = data.get("symbol", "UNKNOWN")
        
        # 简单信号逻辑
        if fast_ma > slow_ma * 1.001:  # 快线上穿慢线
            signal = TradeSignal(
                symbol=symbol,
                signal_type=SignalType.BUY,
                strength=0.8,
                timestamp=data.get("timestamp"),
                price=current_price,
                volume=1.0,
                strategy_id=self.name,
                params={"fast_ma": fast_ma, "slow_ma": slow_ma}
            )
            signals.append(signal)
            self.signals.append(signal)
            
        elif fast_ma < slow_ma * 0.999:  # 快线下穿慢线
            signal = TradeSignal(
                symbol=symbol,
                signal_type=SignalType.SELL,
                strength=-0.8,
                timestamp=data.get("timestamp"),
                price=current_price,
                volume=1.0,
                strategy_id=self.name,
                params={"fast_ma": fast_ma, "slow_ma": slow_ma}
            )
            signals.append(signal)
            self.signals.append(signal)
            
        return signals
        
    def on_signal(self, signal: TradeSignal) -> OrderInfo:
        """
        根据信号生成订单
        
        Args:
            signal: 交易信号
            
        Returns:
            订单信息
        """
        side = OrderSide.BUY if signal.signal_type == SignalType.BUY else OrderSide.SELL
        
        order = OrderInfo(
            order_id="",
            symbol=signal.symbol,
            side=side,
            order_type=OrderType.MARKET,
            quantity=signal.volume,
            price=signal.price,
        )
        
        self.orders.append(order)
        return order
        
    def stop(self):
        """停止策略"""
        self.initialized = False
        print(f"Strategy {self.name} stopped")
        print(f"  Total signals: {len(self.signals)}")
        print(f"  Total orders: {len(self.orders)}")
        
    def get_stats(self) -> Dict[str, Any]:
        """获取策略统计"""
        return {
            "name": self.name,
            "version": self.version,
            "signals_generated": len(self.signals),
            "orders_generated": len(self.orders),
            "data_points_processed": len(self.data_history),
        }
