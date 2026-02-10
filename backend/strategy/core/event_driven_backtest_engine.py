#!/usr/bin/env python3
"""
事件驱动回测引擎

支持完整的事件处理流程、订单管理和持仓跟踪
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum, auto
from loguru import logger
from queue import Queue


class EventType(Enum):
    """事件类型"""
    BAR = auto()           # K线数据
    SIGNAL = auto()        # 交易信号
    ORDER = auto()         # 订单
    TRADE = auto()         # 成交
    POSITION = auto()      # 持仓更新
    ACCOUNT = auto()       # 账户更新


@dataclass
class Event:
    """事件"""
    event_type: EventType
    timestamp: pd.Timestamp
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BarData:
    """K线数据"""
    timestamp: pd.Timestamp
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class Order:
    """订单"""
    order_id: int
    order_type: str  # 'buy' or 'sell'
    size: float
    price: float
    status: str = 'pending'  # pending, completed, cancelled


@dataclass
class Trade:
    """成交记录"""
    trade_id: int
    order_id: int
    timestamp: pd.Timestamp
    size: float
    price: float
    value: float
    fees: float


@dataclass
class Position:
    """持仓"""
    size: float = 0.0
    avg_price: float = 0.0
    
    @property
    def is_long(self) -> bool:
        return self.size > 0
    
    @property
    def is_short(self) -> bool:
        return self.size < 0
    
    @property
    def is_open(self) -> bool:
        return self.size != 0
    
    def update(self, size: float, price: float):
        """更新持仓"""
        if self.size == 0:
            self.size = size
            self.avg_price = price
        else:
            # 计算新的平均价格
            total_value = self.size * self.avg_price + size * price
            self.size += size
            if self.size != 0:
                self.avg_price = total_value / self.size


class EventDrivenBacktestEngine:
    """
    事件驱动回测引擎
    
    与Backtrader的事件驱动架构保持一致:
    1. 使用事件队列处理数据流
    2. 支持多种订单类型
    3. 实时更新持仓和账户
    4. 模拟真实交易环境
    """
    
    def __init__(self):
        """初始化引擎"""
        self.event_queue: Queue = Queue()
        self.handlers: Dict[EventType, List[Callable]] = {}
        
        # 账户状态
        self.cash: float = 0.0
        self.position: Position = Position()
        self.trades: List[Trade] = []
        self.orders: List[Order] = []
        
        # 历史记录
        self.equity_history: List[float] = []
        self.cash_history: List[float] = []
        self.position_history: List[float] = []
        
        # 计数器
        self.order_id_counter: int = 0
        self.trade_id_counter: int = 0
        
        # 注册默认处理器
        self._register_default_handlers()
    
    def _register_default_handlers(self):
        """注册默认事件处理器"""
        self.register(EventType.BAR, self._on_bar)
        self.register(EventType.ORDER, self._on_order)
    
    def register(self, event_type: EventType, handler: Callable):
        """注册事件处理器"""
        if event_type not in self.handlers:
            self.handlers[event_type] = []
        self.handlers[event_type].append(handler)
    
    def put_event(self, event: Event):
        """推送事件到队列"""
        self.event_queue.put(event)
    
    def run_backtest(
        self,
        data: pd.DataFrame,
        signal_generator: Callable[[pd.DataFrame], np.ndarray],
        init_cash: float = 100000.0,
        target: float = 0.5,
        fees: float = 0.0,
        slippage: float = 0.0
    ) -> Dict[str, Any]:
        """
        运行事件驱动回测
        
        Args:
            data: DataFrame with OHLCV data
            signal_generator: Function to generate signals (1=long, -1=short, 0=none)
            init_cash: Initial cash
            target: Target position size (0.5 = 50%)
            fees: Commission fees
            slippage: Slippage
        
        Returns:
            Dict with backtest results
        """
        self.cash = init_cash
        self.position = Position()
        self.trades = []
        self.orders = []
        self.equity_history = []
        self.cash_history = []
        self.position_history = []
        
        # 生成信号
        signals = signal_generator(data)
        
        # 遍历数据，生成事件
        for i in range(len(data)):
            row = data.iloc[i]
            idx = data.index[i]
            timestamp = idx if isinstance(idx, pd.Timestamp) else pd.Timestamp(idx)
            
            # 创建BAR事件
            bar = BarData(
                timestamp=timestamp,
                open=row['Open'],
                high=row['High'],
                low=row['Low'],
                close=row['Close'],
                volume=row['Volume']
            )
            
            # 处理BAR事件
            self._process_bar(bar, signals[i], target, fees, slippage)
            
            # 记录历史
            equity = self._get_equity(bar.close)
            self.equity_history.append(equity)
            self.cash_history.append(self.cash)
            self.position_history.append(self.position.size)
        
        # 计算结果
        return self._calculate_results(init_cash)
    
    def _process_bar(self, bar: BarData, signal: int, target: float, fees: float, slippage: float):
        """处理K线数据"""
        # 使用开盘价执行交易
        exec_price = bar.open
        
        # 计算当前权益
        equity = self._get_equity(exec_price)
        
        # 根据信号执行交易 - 只在信号变化时交易
        if signal == 1 and not self.position.is_long:  # 做多信号且当前非多仓
            self._handle_long_signal(exec_price, target, fees, slippage, bar.timestamp)
        elif signal == -1 and not self.position.is_short:  # 做空信号且当前非空仓
            self._handle_short_signal(exec_price, target, fees, slippage, bar.timestamp)
    
    def _handle_long_signal(self, price: float, target: float, fees: float, slippage: float, timestamp: pd.Timestamp):
        """处理做多信号"""
        # 如果持有空仓，先平空仓
        if self.position.is_short:
            self._close_short_position(price, fees, slippage, timestamp)
        
        # 开多仓
        if not self.position.is_long:
            self._open_long_position(price, target, fees, slippage, timestamp)
    
    def _handle_short_signal(self, price: float, target: float, fees: float, slippage: float, timestamp: pd.Timestamp):
        """处理做空信号"""
        # 如果持有多仓，先平多仓
        if self.position.is_long:
            self._close_long_position(price, fees, slippage, timestamp)
        
        # 开空仓
        if not self.position.is_short:
            self._open_short_position(price, target, fees, slippage, timestamp)
    
    def _open_long_position(self, price: float, target: float, fees: float, slippage: float, timestamp: pd.Timestamp):
        """开多仓"""
        exec_price = price * (1 + slippage)
        
        # 计算目标持仓
        equity = self._get_equity(price)
        target_value = equity * target
        target_size = target_value / exec_price
        
        # 创建订单
        self.order_id_counter += 1
        order = Order(
            order_id=self.order_id_counter,
            order_type='buy',
            size=target_size,
            price=exec_price,
            status='completed'
        )
        self.orders.append(order)
        
        # 执行交易
        trade_value = target_size * exec_price
        trade_fees = trade_value * fees
        total_cost = trade_value + trade_fees
        
        if self.cash >= total_cost:
            self.cash -= total_cost
            self.position.update(target_size, exec_price)
            
            # 记录成交
            self.trade_id_counter += 1
            trade = Trade(
                trade_id=self.trade_id_counter,
                order_id=order.order_id,
                timestamp=timestamp,
                size=target_size,
                price=exec_price,
                value=trade_value,
                fees=trade_fees
            )
            self.trades.append(trade)
            
            logger.debug(f"开多仓: size={target_size:.4f}, price={exec_price:.2f}")
    
    def _close_long_position(self, price: float, fees: float, slippage: float, timestamp: pd.Timestamp):
        """平多仓"""
        if not self.position.is_long:
            return
        
        exec_price = price * (1 - slippage)
        sell_size = self.position.size
        trade_value = sell_size * exec_price
        trade_fees = trade_value * fees
        
        # 创建订单
        self.order_id_counter += 1
        order = Order(
            order_id=self.order_id_counter,
            order_type='sell',
            size=sell_size,
            price=exec_price,
            status='completed'
        )
        self.orders.append(order)
        
        # 执行交易
        self.cash += trade_value - trade_fees
        self.position = Position()
        
        # 记录成交
        self.trade_id_counter += 1
        trade = Trade(
            trade_id=self.trade_id_counter,
            order_id=order.order_id,
            timestamp=timestamp,
            size=sell_size,
            price=exec_price,
            value=trade_value,
            fees=trade_fees
        )
        self.trades.append(trade)
        
        logger.debug(f"平多仓: size={sell_size:.4f}, price={exec_price:.2f}")
    
    def _open_short_position(self, price: float, target: float, fees: float, slippage: float, timestamp: pd.Timestamp):
        """开空仓"""
        exec_price = price * (1 - slippage)
        
        # 计算目标持仓
        equity = self._get_equity(price)
        target_value = equity * target
        target_size = -target_value / exec_price  # 负数表示做空
        
        # 创建订单
        self.order_id_counter += 1
        order = Order(
            order_id=self.order_id_counter,
            order_type='sell',
            size=abs(target_size),
            price=exec_price,
            status='completed'
        )
        self.orders.append(order)
        
        # 执行交易（做空获得现金）
        trade_value = abs(target_size) * exec_price
        trade_fees = trade_value * fees
        self.cash += trade_value - trade_fees
        self.position.update(target_size, exec_price)
        
        # 记录成交
        self.trade_id_counter += 1
        trade = Trade(
            trade_id=self.trade_id_counter,
            order_id=order.order_id,
            timestamp=timestamp,
            size=abs(target_size),
            price=exec_price,
            value=trade_value,
            fees=trade_fees
        )
        self.trades.append(trade)
        
        logger.debug(f"开空仓: size={abs(target_size):.4f}, price={exec_price:.2f}")
    
    def _close_short_position(self, price: float, fees: float, slippage: float, timestamp: pd.Timestamp):
        """平空仓"""
        if not self.position.is_short:
            return
        
        exec_price = price * (1 + slippage)
        buy_size = abs(self.position.size)
        trade_value = buy_size * exec_price
        trade_fees = trade_value * fees
        
        # 创建订单
        self.order_id_counter += 1
        order = Order(
            order_id=self.order_id_counter,
            order_type='buy',
            size=buy_size,
            price=exec_price,
            status='completed'
        )
        self.orders.append(order)
        
        # 执行交易
        self.cash -= trade_value + trade_fees
        self.position = Position()
        
        # 记录成交
        self.trade_id_counter += 1
        trade = Trade(
            trade_id=self.trade_id_counter,
            order_id=order.order_id,
            timestamp=timestamp,
            size=buy_size,
            price=exec_price,
            value=trade_value,
            fees=trade_fees
        )
        self.trades.append(trade)
        
        logger.debug(f"平空仓: size={buy_size:.4f}, price={exec_price:.2f}")
    
    def _on_bar(self, event: Event):
        """处理BAR事件"""
        pass  # 在run_backtest中直接处理
    
    def _on_order(self, event: Event):
        """处理ORDER事件"""
        pass  # 在run_backtest中直接处理
    
    def _get_equity(self, current_price: float) -> float:
        """计算当前权益"""
        position_value = self.position.size * current_price if self.position.is_long else 0
        return self.cash + position_value
    
    def _calculate_results(self, init_cash: float) -> Dict[str, Any]:
        """计算回测结果"""
        equity_array = np.array(self.equity_history)
        
        final_equity = equity_array[-1] if len(equity_array) > 0 else init_cash
        total_return = (final_equity - init_cash) / init_cash * 100
        
        # 计算最大回撤
        peak = np.maximum.accumulate(equity_array)
        drawdown = (equity_array - peak) / peak
        max_drawdown = np.abs(np.min(drawdown)) * 100 if len(drawdown) > 0 else 0
        
        # 计算夏普比率
        if len(equity_array) > 1:
            returns = np.diff(equity_array) / equity_array[:-1]
            std = np.std(returns, ddof=1)
            sharpe = np.mean(returns) / std * np.sqrt(252) if std > 0 else 0
        else:
            sharpe = 0
        
        return {
            'Start Value': init_cash,
            'Equity Final [$]': final_equity,
            'Return [%]': total_return,
            'Max. Drawdown [%]': max_drawdown,
            'Sharpe Ratio': sharpe,
            '# Trades': len(self.trades),
            '# Orders': len(self.orders),
            '_equity_history': equity_array,
            '_cash_history': np.array(self.cash_history),
            '_position_history': np.array(self.position_history),
            '_trades': self.trades,
            '_orders': self.orders,
        }
