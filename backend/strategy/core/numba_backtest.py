#!/usr/bin/env python3
"""
Numba优化的回测执行引擎

提供高性能的JIT编译回测模拟函数
"""

import numpy as np
from numba import njit, prange
from typing import Tuple, Dict, Any


@njit(cache=True, fastmath=True)
def simulate_trades_numba(
    prices: np.ndarray,
    signals: np.ndarray,
    initial_capital: float,
    commission: float,
    slippage: float
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Numba优化的交易模拟
    
    Args:
        prices: 价格数组
        signals: 信号数组 (1=买入, -1=卖出, 0=持有)
        initial_capital: 初始资金
        commission: 手续费率
        slippage: 滑点率
        
    Returns:
        (权益曲线, 现金曲线, 持仓曲线, 交易入场索引, 交易出场索引)
    """
    n = len(prices)
    
    # 初始化数组
    equity = np.zeros(n)
    cash = np.zeros(n)
    position = np.zeros(n)
    
    # 交易记录
    max_trades = n // 2  # 最大交易数量
    entry_indices = np.full(max_trades, -1, dtype=np.int32)
    exit_indices = np.full(max_trades, -1, dtype=np.int32)
    entry_prices = np.zeros(max_trades)
    exit_prices = np.zeros(max_trades)
    trade_sizes = np.zeros(max_trades)
    trade_pnls = np.zeros(max_trades)
    
    current_capital = initial_capital
    current_position = 0.0
    current_entry_price = 0.0
    trade_count = 0
    
    for i in range(n):
        price = prices[i]
        signal = signals[i]
        
        # 计算当前权益
        position_value = current_position * price
        current_equity = current_capital + position_value
        
        equity[i] = current_equity
        cash[i] = current_capital
        position[i] = current_position
        
        # 处理信号
        if signal == 1 and current_position == 0:  # 买入
            # 应用滑点
            entry_price = price * (1 + slippage)
            # 计算仓位大小（扣除手续费）
            position_size = current_capital / entry_price * (1 - commission)
            
            current_position = position_size
            current_capital = 0
            current_entry_price = entry_price
            
            # 记录交易
            if trade_count < max_trades:
                entry_indices[trade_count] = i
                entry_prices[trade_count] = entry_price
                trade_sizes[trade_count] = position_size
                
        elif signal == -1 and current_position > 0:  # 卖出
            # 应用滑点
            exit_price = price * (1 - slippage)
            # 计算卖出价值（扣除手续费）
            sell_value = current_position * exit_price * (1 - commission)
            
            # 计算盈亏
            pnl = sell_value - (trade_sizes[trade_count] * entry_prices[trade_count])
            
            current_capital = sell_value
            current_position = 0
            
            # 记录交易
            if trade_count < max_trades:
                exit_indices[trade_count] = i
                exit_prices[trade_count] = exit_price
                trade_pnls[trade_count] = pnl
                trade_count += 1
    
    # 如果最后还有持仓，计算最终价值
    if current_position > 0 and trade_count > 0 and exit_indices[trade_count - 1] == -1:
        final_price = prices[-1] * (1 - slippage)
        sell_value = current_position * final_price * (1 - commission)
        pnl = sell_value - (trade_sizes[trade_count - 1] * entry_prices[trade_count - 1])
        
        exit_indices[trade_count - 1] = n - 1
        exit_prices[trade_count - 1] = final_price
        trade_pnls[trade_count - 1] = pnl
        
        # 更新最后的权益
        equity[-1] = sell_value
        cash[-1] = sell_value
        position[-1] = 0
    
    return equity, cash, position, entry_indices[:trade_count], exit_indices[:trade_count]


@njit(cache=True, fastmath=True)
def calculate_equity_curve_numba(
    cash: np.ndarray,
    position: np.ndarray,
    prices: np.ndarray
) -> np.ndarray:
    """
    Numba优化的权益曲线计算
    
    Args:
        cash: 现金数组
        position: 持仓数组
        prices: 价格数组
        
    Returns:
        权益曲线数组
    """
    n = len(cash)
    equity = np.zeros(n)
    
    for i in range(n):
        position_value = position[i] * prices[i]
        equity[i] = cash[i] + position_value
    
    return equity


@njit(cache=True, fastmath=True)
def calculate_drawdown_numba(equity: np.ndarray) -> Tuple[np.ndarray, float]:
    """
    Numba优化的回撤计算
    
    Args:
        equity: 权益曲线数组
        
    Returns:
        (回撤数组, 最大回撤值)
    """
    n = len(equity)
    peak = np.zeros(n)
    drawdown = np.zeros(n)
    
    peak[0] = equity[0]
    max_drawdown = 0.0
    
    for i in range(1, n):
        if equity[i] > peak[i-1]:
            peak[i] = equity[i]
        else:
            peak[i] = peak[i-1]
        
        drawdown[i] = (equity[i] - peak[i]) / peak[i]
        if drawdown[i] < max_drawdown:
            max_drawdown = drawdown[i]
    
    return drawdown, max_drawdown


@njit(cache=True, fastmath=True)
def calculate_returns_numba(equity: np.ndarray) -> np.ndarray:
    """
    Numba优化的收益率计算
    
    Args:
        equity: 权益曲线数组
        
    Returns:
        收益率数组
    """
    n = len(equity)
    returns = np.zeros(n)
    
    for i in range(1, n):
        if equity[i-1] != 0:
            returns[i] = (equity[i] - equity[i-1]) / equity[i-1]
    
    return returns


@njit(cache=True, fastmath=True)
def calculate_sharpe_numba(returns: np.ndarray, risk_free_rate: float = 0.0) -> float:
    """
    Numba优化的夏普比率计算
    
    Args:
        returns: 收益率数组
        risk_free_rate: 无风险利率
        
    Returns:
        夏普比率
    """
    # 过滤掉NaN和0值
    valid_returns = returns[returns != 0]
    
    if len(valid_returns) < 2:
        return 0.0
    
    excess_returns = valid_returns - risk_free_rate
    mean_return = np.mean(excess_returns)
    std_return = np.std(excess_returns)
    
    if std_return == 0:
        return 0.0
    
    # 年化夏普比率（假设252个交易日）
    sharpe = mean_return / std_return * np.sqrt(252)
    
    return sharpe


@njit(cache=True, fastmath=True)
def calculate_trade_statistics_numba(
    entry_indices: np.ndarray,
    exit_indices: np.ndarray,
    entry_prices: np.ndarray,
    exit_prices: np.ndarray,
    trade_pnls: np.ndarray
) -> Dict[str, Any]:
    """
    Numba优化的交易统计计算
    
    Args:
        entry_indices: 入场索引数组
        exit_indices: 出场索引数组
        entry_prices: 入场价格数组
        exit_prices: 出场价格数组
        trade_pnls: 盈亏数组
        
    Returns:
        交易统计字典
    """
    n_trades = len(entry_indices)
    
    if n_trades == 0:
        return {
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'win_rate': 0.0,
            'avg_profit': 0.0,
            'avg_loss': 0.0,
            'profit_factor': 0.0,
        }
    
    winning_trades = 0
    losing_trades = 0
    total_profit = 0.0
    total_loss = 0.0
    
    for i in range(n_trades):
        pnl = trade_pnls[i]
        if pnl > 0:
            winning_trades += 1
            total_profit += pnl
        else:
            losing_trades += 1
            total_loss += abs(pnl)
    
    win_rate = winning_trades / n_trades if n_trades > 0 else 0.0
    avg_profit = total_profit / winning_trades if winning_trades > 0 else 0.0
    avg_loss = total_loss / losing_trades if losing_trades > 0 else 0.0
    profit_factor = total_profit / total_loss if total_loss > 0 else 0.0
    
    return {
        'total_trades': n_trades,
        'winning_trades': winning_trades,
        'losing_trades': losing_trades,
        'win_rate': win_rate,
        'avg_profit': avg_profit,
        'avg_loss': avg_loss,
        'profit_factor': profit_factor,
    }


@njit(cache=True, fastmath=True, parallel=True)
def batch_simulate_trades_numba(
    prices_list: list,
    signals_list: list,
    initial_capital: float,
    commission: float,
    slippage: float
) -> list:
    """
    并行批量回测模拟
    
    Args:
        prices_list: 价格数组列表
        signals_list: 信号数组列表
        initial_capital: 初始资金
        commission: 手续费率
        slippage: 滑点率
        
    Returns:
        回测结果列表
    """
    n = len(prices_list)
    results = []
    
    for i in prange(n):
        result = simulate_trades_numba(
            prices_list[i],
            signals_list[i],
            initial_capital,
            commission,
            slippage
        )
        results.append(result)
    
    return results
