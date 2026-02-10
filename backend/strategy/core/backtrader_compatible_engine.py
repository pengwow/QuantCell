#!/usr/bin/env python3
"""
延迟执行回测引擎

核心特性:
1. 延迟执行机制 - 信号次日执行
2. 统一仓位计算 - 基于权益的目标仓位管理
3. 标准化权益计算
"""

import numpy as np
from typing import Dict, Any, Tuple, Optional, List
from dataclasses import dataclass
from enum import Enum
from loguru import logger


class OrderType(Enum):
    """订单类型"""
    BUY = 1
    SELL = -1


class OrderStatus(Enum):
    """订单状态"""
    PENDING = 0
    COMPLETED = 1
    CANCELLED = 2


@dataclass
class Order:
    """订单"""
    order_id: int
    order_type: OrderType
    size: float
    price: float
    status: OrderStatus = OrderStatus.PENDING
    executed_size: float = 0.0
    executed_price: float = 0.0


@dataclass
class Position:
    """持仓"""
    size: float = 0.0
    price: float = 0.0
    
    @property
    def is_long(self) -> bool:
        return self.size > 0
    
    @property
    def is_short(self) -> bool:
        return self.size < 0
    
    @property
    def is_open(self) -> bool:
        return self.size != 0


class DelayedExecutionEngine:
    """
    延迟执行回测引擎
    
    核心特性:
    1. 延迟执行: 信号在次日执行
    2. 仓位计算: 基于权益的目标仓位管理
    3. 权益计算: 标准化权益计算公式
    """
    
    def __init__(self):
        self.cash: float = 0.0
        self.position: Position = Position()
        self.order_id_counter: int = 0
        self.pending_orders: List[Order] = []
        self.trades: List[Dict] = []
        
    def run_backtest(
        self,
        price: np.ndarray,
        signals: np.ndarray,  # 1=做多, -1=做空, 0=无信号
        init_cash: float = 100000.0,
        target: float = 0.5,
        fees: float = 0.0,
        slippage: float = 0.0
    ) -> Dict[str, Any]:
        """
        运行回测
        
        Args:
            price: 价格数组 (使用开盘价执行交易)
            signals: 信号数组 (1=做多, -1=做空, 0=无信号)
            init_cash: 初始资金
            target: 目标仓位比例
            fees: 手续费率
            slippage: 滑点
        
        Returns:
            Dict: 回测结果
        """
        n = len(price)
        self.cash = init_cash
        self.position = Position()
        self.trades = []
        
        # 历史记录
        cash_history = np.zeros(n)
        position_history = np.zeros(n)
        equity_history = np.zeros(n)
        
        # 延迟执行: 使用前一天的信号
        for i in range(1, n):  # 从第2天开始
            current_price = price[i]
            
            # 计算当前权益
            position_value = self.position.size * current_price if self.position.is_long else 0
            equity = self.cash + position_value
            
            # 获取前一天的信号 (延迟执行)
            signal = signals[i-1]
            
            if signal == 1:  # 做多信号
                self._handle_long_signal(current_price, target, fees, slippage, i)
            elif signal == -1:  # 做空信号
                self._handle_short_signal(current_price, target, fees, slippage, i)
            
            # 记录历史
            cash_history[i] = self.cash
            position_history[i] = self.position.size
            equity_history[i] = self._get_equity(current_price)
        
        # 计算指标
        final_equity = equity_history[-1]
        total_return = (final_equity - init_cash) / init_cash * 100
        max_drawdown = self._calculate_max_drawdown(equity_history)
        sharpe = self._calculate_sharpe(equity_history)
        
        return {
            'Start Value': init_cash,
            'Equity Final [$]': final_equity,
            'Return [%]': total_return,
            'Max. Drawdown [%]': max_drawdown,
            'Sharpe Ratio': sharpe,
            '# Trades': len([t for t in self.trades if 'exit' in t.get('type', '')]),
            '_equity_history': equity_history,
            '_position_history': position_history,
            '_cash_history': cash_history,
            '_trades': self.trades,
        }
    
    def _handle_long_signal(self, price: float, target: float, fees: float, slippage: float, step: int):
        """处理做多信号"""
        # 如果持有空仓，先平空仓
        if self.position.is_short:
            self._close_short_position(price, fees, slippage, step)
        
        # 开多仓或调整仓位
        if not self.position.is_long:
            self._open_long_position(price, target, fees, slippage, step)
    
    def _handle_short_signal(self, price: float, target: float, fees: float, slippage: float, step: int):
        """处理做空信号"""
        # 如果持有多仓，先平多仓
        if self.position.is_long:
            self._close_long_position(price, fees, slippage, step)
        
        # 开空仓或调整仓位
        if not self.position.is_short:
            self._open_short_position(price, target, fees, slippage, step)
    
    def _open_long_position(self, price: float, target: float, fees: float, slippage: float, step: int):
        """
        开多仓 - 基于权益的目标仓位管理
        
        关键逻辑:
        1. 计算目标持仓价值 = 权益 * target
        2. 计算目标持仓数量 = 目标价值 / 价格
        3. 买入数量 = 目标数量 - 当前持仓
        """
        exec_price = price * (1 + slippage)
        
        # 计算当前权益
        equity = self._get_equity(price)
        
        # 计算目标持仓数量
        target_value = equity * target
        target_size = target_value / exec_price
        
        # 计算需要买入的数量
        current_size = self.position.size if self.position.is_long else 0
        buy_size = target_size - current_size
        
        if buy_size <= 0:
            return
        
        trade_value = buy_size * exec_price
        trade_fees = trade_value * fees
        total_cost = trade_value + trade_fees
        
        if self.cash >= total_cost:
            self.cash -= total_cost
            self.position = Position(size=target_size, price=exec_price)
            
            self.trades.append({
                'step': step,
                'type': 'entry_long',
                'price': exec_price,
                'size': buy_size,
                'target_size': target_size,
                'value': trade_value,
                'fees': trade_fees,
                'cash': self.cash,
                'equity': equity,
            })
            
            logger.debug(f"开多仓: size={buy_size:.4f}, target={target_size:.4f}, price={exec_price:.2f}")
    
    def _close_long_position(self, price: float, fees: float, slippage: float, step: int):
        """平多仓"""
        if not self.position.is_long:
            return
        
        exec_price = price * (1 - slippage)
        sell_size = self.position.size
        trade_value = sell_size * exec_price
        trade_fees = trade_value * fees
        
        self.cash += trade_value - trade_fees
        
        self.trades.append({
            'step': step,
            'type': 'exit_long',
            'price': exec_price,
            'size': sell_size,
            'value': trade_value,
            'fees': trade_fees,
            'cash': self.cash,
        })
        
        self.position = Position()
        logger.debug(f"平多仓: size={sell_size:.4f}, price={exec_price:.2f}")
    
    def _open_short_position(self, price: float, target: float, fees: float, slippage: float, step: int):
        """
        开空仓 - 基于权益的目标仓位管理
        
        关键逻辑:
        1. 计算目标持仓价值 = 权益 * target
        2. 计算目标持仓数量 = -目标价值 / 价格 (负数表示做空)
        3. 卖出数量 = 目标数量 - 当前持仓
        """
        exec_price = price * (1 - slippage)
        
        # 计算当前权益
        equity = self._get_equity(price)
        
        # 计算目标持仓数量
        target_value = equity * target
        target_size = -target_value / exec_price
        
        # 计算需要卖出的数量
        current_size = self.position.size if self.position.is_short else 0
        sell_size = abs(target_size) - abs(current_size)
        
        if sell_size <= 0:
            return
        
        trade_value = sell_size * exec_price
        trade_fees = trade_value * fees
        
        # 做空获得现金
        self.cash += trade_value - trade_fees
        self.position = Position(size=target_size, price=exec_price)
        
        self.trades.append({
            'step': step,
            'type': 'entry_short',
            'price': exec_price,
            'size': sell_size,
            'target_size': target_size,
            'value': trade_value,
            'fees': trade_fees,
            'cash': self.cash,
            'equity': equity,
        })
        
        logger.debug(f"开空仓: size={sell_size:.4f}, target={target_size:.4f}, price={exec_price:.2f}")
    
    def _close_short_position(self, price: float, fees: float, slippage: float, step: int):
        """平空仓"""
        if not self.position.is_short:
            return
        
        exec_price = price * (1 + slippage)
        buy_size = abs(self.position.size)
        trade_value = buy_size * exec_price
        trade_fees = trade_value * fees
        
        self.cash -= trade_value + trade_fees
        
        self.trades.append({
            'step': step,
            'type': 'exit_short',
            'price': exec_price,
            'size': buy_size,
            'value': trade_value,
            'fees': trade_fees,
            'cash': self.cash,
        })
        
        self.position = Position()
        logger.debug(f"平空仓: size={buy_size:.4f}, price={exec_price:.2f}")
    
    def _get_equity(self, current_price: float) -> float:
        """
        计算当前权益
        
        权益 = 现金 + 持仓市值
        """
        position_value = self.position.size * current_price if self.position.is_long else 0
        return self.cash + position_value
    
    def _calculate_max_drawdown(self, equity_history: np.ndarray) -> float:
        """计算最大回撤"""
        peak = np.maximum.accumulate(equity_history)
        drawdown = (equity_history - peak) / peak
        return np.abs(np.min(drawdown)) * 100
    
    def _calculate_sharpe(self, equity_history: np.ndarray) -> float:
        """计算夏普比率"""
        returns = np.diff(equity_history) / equity_history[:-1]
        if len(returns) < 2:
            return 0.0
        std = np.std(returns, ddof=1)
        if std == 0 or np.isnan(std):
            return 0.0
        return np.mean(returns) / std * np.sqrt(252)
