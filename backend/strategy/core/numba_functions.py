# Numba JIT 编译的性能函数
# 替代 Cython 实现，简化环境依赖

import numpy as np
from numba import njit, prange
from typing import Tuple


@njit(cache=True, fastmath=True)
def simulate_orders(price: np.ndarray,
                       size: np.ndarray,
                       direction: np.ndarray,
                       fees: float,
                       slippage: float,
                       init_cash: float) -> Tuple[np.ndarray, np.ndarray]:
    """
    Numba JIT 编译的订单模拟函数
    
    参数：
    - price: 价格数组 (时间 × 资产)
    - size: 订单大小数组
    - direction: 订单方向数组 (0=short, 1=long)
    - fees: 手续费率
    - slippage: 滑点
    - init_cash: 初始资金
    
    返回：
    - tuple: (cash, positions)
    """
    n_steps = price.shape[0]
    n_assets = price.shape[1]
    
    # 初始化状态数组
    cash = np.full(n_assets, init_cash, dtype=np.float64)
    positions = np.zeros((n_steps, n_assets), dtype=np.float64)
    
    # 遍历每个时间步
    for i in range(n_steps):
        for j in range(n_assets):
            # 获取当前价格
            current_price = price[i, j]
            
            # 检查是否有订单
            if size[i, j] != 0:
                # 计算滑点后的价格
                if direction[i, j] == 1:  # long
                    exec_price = current_price * (1.0 + slippage)
                    req_cash = size[i, j] * exec_price * (1.0 + fees)
                    
                    if cash[j] >= req_cash:
                        # 执行买入
                        cash[j] -= req_cash
                        positions[i, j] += size[i, j]
                else:  # short
                    exec_price = current_price * (1.0 - slippage)
                    req_cash = size[i, j] * exec_price * (1.0 + fees)
                    
                    if positions[i, j] >= size[i, j]:
                        # 执行卖出
                        cash[j] += req_cash
                        positions[i, j] -= size[i, j]
    
    return cash, positions


@njit(cache=True, fastmath=True)
def calculate_trades(price: np.ndarray,
                   positions: np.ndarray,
                   fees: float) -> np.ndarray:
    """
    Numba JIT 编译的交易记录计算函数
    
    参数：
    - price: 价格数组
    - positions: 持仓数组
    - fees: 手续费率
    
    返回：
    - np.ndarray: 交易记录数组
    """
    n_steps = price.shape[0]
    n_assets = price.shape[1]
    
    # 计算交易记录（简化版本，只返回交易数量）
    trade_count = 0
    
    for i in range(1, n_steps):
        for j in range(n_assets):
            if positions[i, j] != positions[i-1, j]:
                trade_count += 1
    
    return np.array([trade_count], dtype=np.float64)


@njit(cache=True, fastmath=True)
def signals_to_orders(entries: np.ndarray,
                   exits: np.ndarray,
                   size: float) -> tuple:
    """
    Numba JIT 编译的信号转换函数
    
    参数：
    - entries: 入场信号数组
    - exits: 出场信号数组
    - size: 订单大小
    
    返回：
    - tuple: (size_arr, direction_arr)
    """
    n_steps = entries.shape[0]
    n_assets = entries.shape[1]
    
    # 初始化订单数组
    size_arr = np.zeros((n_steps, n_assets), dtype=np.float64)
    direction_arr = np.zeros((n_steps, n_assets), dtype=np.int32)
    
    # 遍历每个时间步
    for i in range(n_steps):
        for j in range(n_assets):
            # 检查入场信号
            if entries[i, j]:
                size_arr[i, j] = size
                direction_arr[i, j] = 1  # long
            # 检查出场信号
            elif exits[i, j]:
                size_arr[i, j] = -size
                direction_arr[i, j] = 0  # short
    
    return size_arr, direction_arr


@njit(cache=True, fastmath=True)
def calculate_metrics(trades_pnl: np.ndarray,
                   trades_fees: np.ndarray,
                   trades_value: np.ndarray,
                   cash: np.ndarray) -> np.ndarray:
    """
    Numba JIT 编译的指标计算函数
    
    参数：
    - trades_pnl: 交易盈亏数组
    - trades_fees: 交易手续费数组
    - trades_value: 交易价值数组
    - cash: 最终现金数组
    
    返回：
    - np.ndarray: 包含各种绩效指标的数组
    """
    n_trades = len(trades_pnl)
    
    # 计算总盈亏
    total_pnl = 0.0
    total_fees = 0.0
    win_trades = 0
    
    for i in range(n_trades):
        total_pnl += trades_pnl[i]
        total_fees += trades_fees[i]
        if trades_pnl[i] > 0:
            win_trades += 1
    
    # 计算胜率
    win_rate = 0.0
    if n_trades > 0:
        win_rate = win_trades / n_trades
    
    # 计算夏普比率（简化版本）
    sharpe_ratio = 0.0
    if n_trades > 1:
        # 计算每笔交易的收益率
        returns = np.zeros(n_trades, dtype=np.float64)
        for i in range(n_trades):
            if trades_value[i] > 0:
                returns[i] = trades_pnl[i] / trades_value[i]
        
        # 计算平均收益率
        mean_return = 0.0
        for i in range(n_trades):
            mean_return += returns[i]
        mean_return /= n_trades
        
        # 计算标准差
        std_return = 0.0
        for i in range(n_trades):
            std_return += (returns[i] - mean_return) ** 2
        std_return = np.sqrt(std_return / n_trades)
        
        # 计算夏普比率
        if std_return > 0:
            sharpe_ratio = mean_return / std_return * np.sqrt(252.0)
    
    # 计算最终权益
    final_equity = 0.0
    if len(cash) > 0:
        for i in range(len(cash)):
            final_equity += cash[i]
    
    return np.array([total_pnl, total_fees, win_rate, sharpe_ratio, n_trades, final_equity], dtype=np.float64)


@njit(cache=True, fastmath=True)
def calculate_funding_rate(index_price: float,
                      mark_price: float) -> float:
    """
    Numba JIT 编译的资金费率计算函数
    
    参数：
    - index_price: 指数价格
    - mark_price: 标记价格
    
    返回：
    - float: 资金费率
    """
    funding_rate = (mark_price - index_price) / index_price
    
    # 限制在 ±0.75% 之间
    if funding_rate > 0.0075:
        funding_rate = 0.0075
    elif funding_rate < -0.0075:
        funding_rate = -0.0075
    
    return funding_rate


@njit(cache=True, fastmath=True)
def calculate_funding_payment(position_size: float,
                         funding_rate: float) -> float:
    """
    Numba JIT 编译的资金费支付计算函数
    
    参数：
    - position_size: 持仓大小
    - funding_rate: 资金费率
    
    返回：
    - float: 资金费支付金额
    """
    return position_size * funding_rate
