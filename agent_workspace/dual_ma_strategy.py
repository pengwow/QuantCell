"""
双均线交叉策略

基于快速移动平均线和慢速移动平均线的交叉信号进行交易。
当快速均线上穿慢速均线时买入，当快速均线下穿慢速均线时卖出。
"""

from typing import Any, Dict, List
from datetime import datetime
from enum import Enum
import numpy as np


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


class DualMAStrategy:
    """双均线交叉策略"""
    
    def __init__(self, params: Dict[str, Any] = None):
        """
        初始化策略
        
        Args:
            params: 策略参数，包含：
                - fast_period: 快速均线周期（默认10）
                - slow_period: 慢速均线周期（默认30）
                - ma_type: 均线类型（SMA/EMA，默认SMA）
                - stop_loss: 止损比例（默认0.05）
                - take_profit: 止盈比例（默认0.10）
        """
        self.params = params or {}
        self.name = "DualMAStrategy"
        self.version = "1.0.0"
        
        # 策略参数
        self.fast_period = self.params.get("fast_period", 10)
        self.slow_period = self.params.get("slow_period", 30)
        self.ma_type = self.params.get("ma_type", "SMA").upper()
        self.stop_loss = self.params.get("stop_loss", 0.05)
        self.take_profit = self.params.get("take_profit", 0.10)
        
        # 验证参数
        if self.fast_period >= self.slow_period:
            raise ValueError(f"快速均线周期({self.fast_period})必须小于慢速均线周期({self.slow_period})")
        
        # 状态
        self.initialized = False
        self.data_history: List[Dict[str, Any]] = []
        self.signals: List[TradeSignal] = []
        self.position = 0  # 0: 无持仓, 1: 多头, -1: 空头
        self.entry_price = 0.0
        
    def initialize(self):
        """初始化策略"""
        self.initialized = True
        print(f"策略 {self.name} v{self.version} 已初始化")
        print(f"  快速均线周期: {self.fast_period}")
        print(f"  慢速均线周期: {self.slow_period}")
        print(f"  均线类型: {self.ma_type}")
        print(f"  止损: {self.stop_loss*100:.1f}%")
        print(f"  止盈: {self.take_profit*100:.1f}%")
        
    def calculate_ma(self, data: List[float], period: int) -> float:
        """
        计算移动平均线
        
        Args:
            data: 价格数据
            period: 周期
            
        Returns:
            移动平均值
        """
        if len(data) < period:
            return np.nan
            
        if self.ma_type == "EMA":
            # 指数移动平均
            return self._calculate_ema(data, period)
        else:
            # 简单移动平均
            return np.mean(data[-period:])
    
    def _calculate_ema(self, data: List[float], period: int) -> float:
        """计算指数移动平均"""
        if len(data) < period:
            return np.nan
            
        # EMA计算公式
        multiplier = 2 / (period + 1)
        ema = data[0]
        
        for price in data[1:]:
            ema = (price - ema) * multiplier + ema
            
        return ema
    
    def on_data(self, data: Dict[str, Any]) -> List[TradeSignal]:
        """
        处理市场数据
        
        Args:
            data: 市场数据字典，包含：
                - symbol: 交易对
                - timestamp: 时间戳
                - open: 开盘价
                - high: 最高价
                - low: 最低价
                - close: 收盘价
                - volume: 成交量
            
        Returns:
            交易信号列表
        """
        if not self.initialized:
            self.initialize()
            
        # 保存数据历史
        self.data_history.append(data)
        
        # 保持历史数据长度
        max_history = self.slow_period + 10
        if len(self.data_history) > max_history:
            self.data_history.pop(0)
            
        # 生成信号
        signals = self._generate_signals(data)
        
        return signals
    
    def _generate_signals(self, data: Dict[str, Any]) -> List[TradeSignal]:
        """生成交易信号"""
        signals = []
        
        if len(self.data_history) < self.slow_period:
            return signals
            
        # 获取收盘价历史
        closes = [d.get("close", 0) for d in self.data_history]
        
        # 计算均线
        fast_ma = self.calculate_ma(closes, self.fast_period)
        slow_ma = self.calculate_ma(closes, self.slow_period)
        
        if np.isnan(fast_ma) or np.isnan(slow_ma):
            return signals
            
        # 获取当前价格和交易对
        current_price = data.get("close", 0)
        symbol = data.get("symbol", "UNKNOWN")
        timestamp = data.get("timestamp", datetime.now())
        
        # 检查止损止盈
        if self.position != 0:
            price_change = (current_price - self.entry_price) / self.entry_price
            
            # 止损检查
            if price_change <= -self.stop_loss:
                signal_type = SignalType.SELL if self.position == 1 else SignalType.BUY
                signal = TradeSignal(
                    symbol=symbol,
                    signal_type=signal_type,
                    strength=-1.0,
                    timestamp=timestamp,
                    price=current_price,
                    volume=1.0,
                    strategy_id=self.name,
                    params={
                        "fast_ma": fast_ma,
                        "slow_ma": slow_ma,
                        "reason": "stop_loss",
                        "pnl": price_change
                    }
                )
                signals.append(signal)
                self.signals.append(signal)
                self.position = 0
                return signals
                
            # 止盈检查
            if price_change >= self.take_profit:
                signal_type = SignalType.SELL if self.position == 1 else SignalType.BUY
                signal = TradeSignal(
                    symbol=symbol,
                    signal_type=signal_type,
                    strength=1.0,
                    timestamp=timestamp,
                    price=current_price,
                    volume=1.0,
                    strategy_id=self.name,
                    params={
                        "fast_ma": fast_ma,
                        "slow_ma": slow_ma,
                        "reason": "take_profit",
                        "pnl": price_change
                    }
                )
                signals.append(signal)
                self.signals.append(signal)
                self.position = 0
                return signals
        
        # 均线交叉信号
        # 金叉：快速均线上穿慢速均线
        if fast_ma > slow_ma * 1.001:  # 0.1%的缓冲区避免频繁交易
            if self.position <= 0:  # 无持仓或空头持仓
                signal = TradeSignal(
                    symbol=symbol,
                    signal_type=SignalType.BUY,
                    strength=0.8,
                    timestamp=timestamp,
                    price=current_price,
                    volume=1.0,
                    strategy_id=self.name,
                    params={
                        "fast_ma": fast_ma,
                        "slow_ma": slow_ma,
                        "reason": "golden_cross"
                    }
                )
                signals.append(signal)
                self.signals.append(signal)
                self.position = 1
                self.entry_price = current_price
                
        # 死叉：快速均线下穿慢速均线
        elif fast_ma < slow_ma * 0.999:  # 0.1%的缓冲区
            if self.position >= 0:  # 无持仓或多头持仓
                signal = TradeSignal(
                    symbol=symbol,
                    signal_type=SignalType.SELL,
                    strength=-0.8,
                    timestamp=timestamp,
                    price=current_price,
                    volume=1.0,
                    strategy_id=self.name,
                    params={
                        "fast_ma": fast_ma,
                        "slow_ma": slow_ma,
                        "reason": "death_cross"
                    }
                )
                signals.append(signal)
                self.signals.append(signal)
                self.position = -1
                self.entry_price = current_price
                
        return signals
    
    def stop(self):
        """停止策略"""
        self.initialized = False
        print(f"策略 {self.name} 已停止")
        print(f"  总信号数: {len(self.signals)}")
        print(f"  当前持仓: {self.position}")
        
    def get_stats(self) -> Dict[str, Any]:
        """获取策略统计"""
        buy_signals = [s for s in self.signals if s.signal_type == SignalType.BUY]
        sell_signals = [s for s in self.signals if s.signal_type == SignalType.SELL]
        
        return {
            "name": self.name,
            "version": self.version,
            "fast_period": self.fast_period,
            "slow_period": self.slow_period,
            "ma_type": self.ma_type,
            "total_signals": len(self.signals),
            "buy_signals": len(buy_signals),
            "sell_signals": len(sell_signals),
            "current_position": self.position,
            "data_points_processed": len(self.data_history),
        }
    
    def get_signal_history(self) -> List[Dict[str, Any]]:
        """获取信号历史"""
        history = []
        for signal in self.signals:
            history.append({
                "timestamp": signal.timestamp,
                "symbol": signal.symbol,
                "signal_type": signal.signal_type.value,
                "strength": signal.strength,
                "price": signal.price,
                "params": signal.params
            })
        return history


# 策略参数示例
DEFAULT_PARAMS = {
    "fast_period": 10,    # 快速均线周期
    "slow_period": 30,    # 慢速均线周期
    "ma_type": "SMA",     # 均线类型：SMA/EMA
    "stop_loss": 0.05,    # 止损比例：5%
    "take_profit": 0.10,  # 止盈比例：10%
}


def create_strategy(params: Dict[str, Any] = None) -> DualMAStrategy:
    """创建策略实例的工厂函数"""
    if params is None:
        params = DEFAULT_PARAMS
    return DualMAStrategy(params)


if __name__ == "__main__":
    # 测试策略
    strategy = create_strategy()
    
    # 模拟数据
    test_data = [
        {"symbol": "BTCUSDT", "close": 50000, "timestamp": datetime(2024, 1, 1)},
        {"symbol": "BTCUSDT", "close": 51000, "timestamp": datetime(2024, 1, 2)},
        {"symbol": "BTCUSDT", "close": 52000, "timestamp": datetime(2024, 1, 3)},
        # ... 更多数据
    ]
    
    for data in test_data:
        signals = strategy.on_data(data)
        for signal in signals:
            print(f"信号: {signal.signal_type.value} @ {signal.price}")