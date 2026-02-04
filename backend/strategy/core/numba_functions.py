# Numba JIT 编译的性能函数

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
    
    修复问题：
    1. 现金应该是单一值，不是每个资产都有独立现金
    2. 持仓需要正确传递
    3. 卖出时应该释放资金
    
    参数：
    - price: 价格数组 (时间 × 资产)
    - size: 订单大小数组
    - direction: 订单方向数组 (0=short, 1=long)
    - fees: 手续费率
    - slippage: 滑点
    - init_cash: 初始资金
    
    返回：
    - tuple: (cash_history, positions_history)
    """
    n_steps = price.shape[0]
    n_assets = price.shape[1]
    
    # 初始化状态 - 单一现金池
    cash = init_cash
    current_position = 0.0
    
    # 记录每个时间步的现金和持仓
    cash_history = np.zeros(n_steps, dtype=np.float64)
    positions_history = np.zeros((n_steps, n_assets), dtype=np.float64)
    
    # 遍历每个时间步
    for i in range(n_steps):
        for j in range(n_assets):
            # 获取当前价格
            current_price = price[i, j]
            
            # 检查是否有订单（size > 0 表示买入，size < 0 表示卖出）
            if size[i, j] > 0:  # 买入信号
                # 避免重复买入：如果已经有持仓，不再买入
                if current_position <= 0:
                    exec_price = current_price * (1.0 + slippage)
                    trade_value = size[i, j] * exec_price
                    trade_fees = trade_value * fees
                    total_cost = trade_value + trade_fees
                    
                    # 检查是否有足够资金
                    if cash >= total_cost:
                        # 执行买入
                        cash -= total_cost
                        current_position += size[i, j]
            elif size[i, j] < 0:  # 卖出信号
                # 避免重复卖出：如果没有持仓，不再卖出
                if current_position > 0:
                    exec_price = current_price * (1.0 - slippage)
                    sell_size = min(abs(size[i, j]), current_position)  # 卖出数量不能超过持仓
                    
                    if sell_size > 0:
                        trade_value = sell_size * exec_price
                        trade_fees = trade_value * fees
                        net_proceeds = trade_value - trade_fees
                        
                        # 执行卖出
                        cash += net_proceeds
                        current_position -= sell_size
            
            # 记录当前持仓
            positions_history[i, j] = current_position
        
        # 记录当前现金
        cash_history[i] = cash
    
    return cash_history, positions_history


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
    
    修复：cash 现在是现金历史数组，取最后一个值作为最终现金
    
    参数：
    - trades_pnl: 交易盈亏数组
    - trades_fees: 交易手续费数组
    - trades_value: 交易价值数组
    - cash: 现金历史数组（每个时间步的现金余额）
    
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
    
    # 计算最终权益 - cash 是历史数组，取最后一个值
    final_equity = 0.0
    if len(cash) > 0:
        final_equity = cash[-1]  # 取最后一个时间步的现金
    
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


@njit(cache=True, fastmath=True)
def check_stop_loss(current_price: float,
                   entry_price: float,
                   direction: int,
                   stop_loss: float) -> bool:
    """
    Numba JIT 编译的止损检查函数

    参数：
    - current_price: 当前价格
    - entry_price: 入场价格
    - direction: 方向 (1=long, 0=short)
    - stop_loss: 止损比例

    返回：
    - bool: 是否触发止损
    """
    if stop_loss <= 0.0:
        return False

    if direction == 1:  # long
        pnl = current_price - entry_price
        if pnl < 0.0 and abs(pnl) >= entry_price * stop_loss:
            return True
    else:  # short
        pnl = entry_price - current_price
        if pnl < 0.0 and abs(pnl) >= entry_price * stop_loss:
            return True

    return False


@njit(cache=True, fastmath=True)
def check_take_profit(current_price: float,
                     entry_price: float,
                     direction: int,
                     take_profit: float) -> bool:
    """
    Numba JIT 编译的止盈检查函数

    参数：
    - current_price: 当前价格
    - entry_price: 入场价格
    - direction: 方向 (1=long, 0=short)
    - take_profit: 止盈比例

    返回：
    - bool: 是否触发止盈
    """
    if take_profit <= 0.0:
        return False

    if direction == 1:  # long
        pnl = current_price - entry_price
        if pnl > 0.0 and pnl >= entry_price * take_profit:
            return True
    else:  # short
        pnl = entry_price - current_price
        if pnl > 0.0 and pnl >= entry_price * take_profit:
            return True

    return False


@njit(cache=True, fastmath=True)
def adjust_position(current_price: float,
                   entry_price: float,
                   direction: int,
                   position_size: float,
                   max_position_size: float,
                   position_adjustment_enabled: bool) -> float:
    """
    Numba JIT 编译的仓位调整函数

    参数：
    - current_price: 当前价格
    - entry_price: 入场价格
    - direction: 方向 (1=long, 0=short)
    - position_size: 当前仓位大小
    - max_position_size: 最大仓位大小
    - position_adjustment_enabled: 是否启用仓位调整

    返回：
    - float: 调整后的仓位大小
    """
    if not position_adjustment_enabled:
        return position_size

    if max_position_size <= 0.0:
        return position_size

    pnl = 0.0
    if direction == 1:  # long
        pnl = current_price - entry_price
    else:  # short
        pnl = entry_price - current_price

    if pnl > 0.0:
        new_size = position_size * 1.5
        if new_size > max_position_size:
            new_size = max_position_size
        return new_size

    return position_size
