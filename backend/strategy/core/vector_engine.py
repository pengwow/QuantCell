# 向量引擎
# 用于回测模式的高性能向量化计算

import numpy as np
from typing import Dict, Any
from loguru import logger


class VectorEngine:
    """
    向量引擎
    用于回测模式的高性能向量化计算
    使用 Numba JIT 编译提升性能
    """
    
    def __init__(self):
        """
        初始化向量引擎
        """
        self.cash = None
        self.positions = None
        self.orders = None
        self.trades = None
        
        # 新增：风险控制
        self.stop_losses = None
        self.take_profits = None
        self.position_adjustments = None
        
        # 尝试导入 Numba 编译函数
        try:
            from .numba_functions import (
                simulate_orders,
                signals_to_orders,
                calculate_metrics,
                calculate_funding_rate,
                calculate_funding_payment,
                # 新增：风险控制函数
                check_stop_loss,
                check_take_profit,
                adjust_position,
            )
            
            self.simulate_orders = simulate_orders
            self.signals_to_orders = signals_to_orders
            self.calculate_metrics = calculate_metrics
            self.calculate_funding_rate = calculate_funding_rate
            self.calculate_funding_payment = calculate_funding_payment
            self.check_stop_loss = check_stop_loss
            self.check_take_profit = check_take_profit
            self.adjust_position = adjust_position
            
            logger.info("使用 Numba JIT 编译模块（高性能模式）")
        except ImportError as e:
            # 如果 Numba 未安装，使用 Python 实现
            self.simulate_orders = self._simulate_orders_python
            self.signals_to_orders = self._signals_to_orders_python
            self.calculate_metrics = self._calculate_metrics_python
            self.calculate_funding_rate = self._calculate_funding_rate_python
            self.calculate_funding_payment = self._calculate_funding_payment_python
            self.check_stop_loss = self._check_stop_loss_python
            self.check_take_profit = self._check_take_profit_python
            self.adjust_position = self._adjust_position_python
            
            logger.warning(f"Numba 未安装，使用 Python 实现（性能较低）：{e}")
    
    def run_backtest(self, price: np.ndarray, 
                   entries: np.ndarray,
                   exits: np.ndarray,
                   init_cash: float = 100000.0,
                   fees: float = 0.001,
                   slippage: float = 0.0001) -> Dict[str, Any]:
        """
        运行向量回测
        
        参数：
        - price: 价格数组 (时间 × 资产)
        - entries: 入场信号数组
        - exits: 出场信号数组
        - init_cash: 初始资金
        - fees: 手续费率
        - slippage: 滑点
        
        返回：
        - dict: 回测结果
        """
        # 从信号生成订单
        size_arr, direction_arr = self.signals_to_orders(
            entries=entries,
            exits=exits,
            size=1.0
        )
        
        # 运行订单模拟
        cash, positions = self.simulate_orders(
            price=price,
            size=size_arr,
            direction=direction_arr,
            fees=fees,
            slippage=slippage,
            init_cash=init_cash
        )
        
        # 计算交易记录
        trades = self._calculate_trades(price, positions, fees)
        
        # 计算绩效指标
        if len(trades) > 0:
            trades_pnl = np.array([t['pnl'] for t in trades], dtype=np.float64)
            trades_fees = np.array([t['fees'] for t in trades], dtype=np.float64)
            trades_value = np.array([t['value'] for t in trades], dtype=np.float64)
        else:
            trades_pnl = np.array([])
            trades_fees = np.array([])
            trades_value = np.array([])
        
        metrics_arr = self.calculate_metrics(
            trades_pnl=trades_pnl,
            trades_fees=trades_fees,
            trades_value=trades_value,
            cash=cash
        )
        
        metrics = {
            'total_pnl': float(metrics_arr[0]),
            'total_fees': float(metrics_arr[1]),
            'win_rate': float(metrics_arr[2]),
            'sharpe_ratio': float(metrics_arr[3]),
            'trade_count': int(metrics_arr[4]),
            'final_equity': float(metrics_arr[5])
        }
        
        return {
            'cash': cash,
            'positions': positions,
            'orders': [],
            'trades': trades,
            'metrics': metrics
        }
    
    def _calculate_trades(self, price: np.ndarray,
                         positions: np.ndarray,
                         fees: float) -> np.ndarray:
        """
        计算交易记录
        
        参数：
        - price: 价格数组
        - positions: 持仓数组
        - fees: 手续费率
        
        返回：
        - np.ndarray: 交易记录数组
        """
        n_steps = price.shape[0]
        n_assets = price.shape[1]
        
        trades_list = []
        
        for i in range(1, n_steps):
            for j in range(n_assets):
                if positions[i, j] != positions[i-1, j]:
                    # 持仓变化，生成交易记录
                    trade_size = positions[i, j] - positions[i-1, j]
                    trade_price = price[i, j]
                    trade_value = abs(trade_size) * trade_price
                    trade_fees = trade_value * fees
                    
                    trades_list.append({
                        'step': i,
                        'asset': j,
                        'direction': 'long' if trade_size > 0 else 'short',
                        'size': abs(trade_size),
                        'price': trade_price,
                        'value': trade_value,
                        'fees': trade_fees,
                        'pnl': -trade_fees if trade_size > 0 else trade_fees
                    })
        
        return np.array(trades_list, dtype=object)
    
    def _signals_to_orders_python(self, entries: np.ndarray,
                                 exits: np.ndarray,
                                 size: float = 1.0) -> tuple:
        """
        Python 版本的信号转换（备用）
        """
        n_steps, n_assets = entries.shape
        
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
    
    def _simulate_orders_python(self, price: np.ndarray,
                               size: np.ndarray,
                               direction: np.ndarray,
                               fees: float,
                               slippage: float,
                               init_cash: float) -> tuple:
        """
        Python 版本的订单模拟（备用）
        
        修复问题：
        1. 现金应该是单一值，不是每个资产都有独立现金
        2. 持仓需要正确传递
        3. 卖出时应该释放资金
        """
        n_steps, n_assets = price.shape
        
        # 初始化状态 - 单一现金池
        cash = init_cash
        current_position = 0.0  # 当前持仓量
        
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
                        exec_price = current_price * (1 + slippage)
                        trade_value = size[i, j] * exec_price
                        trade_fees = trade_value * fees
                        total_cost = trade_value + trade_fees
                        
                        # 检查是否有足够资金
                        if cash >= total_cost:
                            cash -= total_cost
                            current_position += size[i, j]
                            logger.debug(f"买入: 价格={exec_price:.2f}, 数量={size[i, j]}, 成本={total_cost:.2f}, 剩余现金={cash:.2f}")
                        else:
                            logger.warning(f"资金不足，无法买入: 需要={total_cost:.2f}, 可用={cash:.2f}")
                
                elif size[i, j] < 0:  # 卖出信号
                    # 避免重复卖出：如果没有持仓，不再卖出
                    if current_position > 0:
                        exec_price = current_price * (1 - slippage)
                        sell_size = min(abs(size[i, j]), current_position)  # 卖出数量不能超过持仓
                        
                        if sell_size > 0:
                            trade_value = sell_size * exec_price
                            trade_fees = trade_value * fees
                            net_proceeds = trade_value - trade_fees
                            
                            cash += net_proceeds
                            current_position -= sell_size
                            logger.debug(f"卖出: 价格={exec_price:.2f}, 数量={sell_size}, 收入={net_proceeds:.2f}, 剩余现金={cash:.2f}")
                        else:
                            logger.warning(f"持仓不足，无法卖出: 需要={sell_size}, 可用={current_position}")
                
                # 记录当前持仓
                positions_history[i, j] = current_position
            
            # 记录当前现金
            cash_history[i] = cash
        
        return cash_history, positions_history
    
    def _calculate_metrics_python(self, trades: np.ndarray,
                               cash: np.ndarray) -> Dict[str, Any]:
        """
        Python 版本的指标计算（备用）
        """
        if len(trades) == 0:
            return {}
        
        total_pnl = np.sum(trades['pnl'])
        total_fees = np.sum(trades['fees'])
        win_trades = np.sum(trades['pnl'] > 0)
        win_rate = win_trades / len(trades)
        
        # 计算夏普比率（简化版本）
        if len(trades) > 1:
            # 计算每笔交易的收益率
            returns = trades['pnl'] / trades['value']
            
            # 计算平均收益率和标准差
            mean_return = np.mean(returns)
            std_return = np.std(returns)
            
            # 计算夏普比率
            if std_return > 0:
                sharpe_ratio = mean_return / std_return * np.sqrt(252)
            else:
                sharpe_ratio = 0.0
        else:
            sharpe_ratio = 0.0
        
        # 计算最终权益 - cash 是历史数组，取最后一个值
        final_equity = float(cash[-1]) if len(cash) > 0 else 0.0
        
        return {
            'total_pnl': float(total_pnl),
            'total_fees': float(total_fees),
            'win_rate': float(win_rate),
            'sharpe_ratio': float(sharpe_ratio),
            'trade_count': len(trades),
            'final_equity': final_equity
        }
    
    def _calculate_funding_rate_python(self, index_price: float,
                                    mark_price: float) -> float:
        """
        Python 版本的资金费率计算（备用）
        """
        funding_rate = (mark_price - index_price) / index_price
        
        # 限制在 ±0.75% 之间
        if funding_rate > 0.0075:
            funding_rate = 0.0075
        elif funding_rate < -0.0075:
            funding_rate = -0.0075
        
        return funding_rate
    
    def _calculate_funding_payment_python(self, position_size: float,
                                       funding_rate: float) -> float:
        """
        Python 版本的资金费支付计算（备用）
        """
        return position_size * funding_rate
    
    def _check_stop_loss_python(self, current_price: float, 
                               entry_price: float, 
                               direction: int,
                               stop_loss: float) -> bool:
        """
        Python 版本的止损检查（备用）
        """
        if stop_loss <= 0:
            return False
        
        if direction == 1:
            pnl = (current_price - entry_price)
            if pnl < 0 and abs(pnl) >= entry_price * stop_loss:
                return True
        else:
            pnl = (entry_price - current_price)
            if pnl < 0 and abs(pnl) >= entry_price * stop_loss:
                return True
        
        return False
    
    def _check_take_profit_python(self, current_price: float, 
                                 entry_price: float, 
                                 direction: int,
                                 take_profit: float) -> bool:
        """
        Python 版本的止盈检查（备用）
        """
        if take_profit <= 0:
            return False
        
        if direction == 1:
            pnl = (current_price - entry_price)
            if pnl > 0 and pnl >= entry_price * take_profit:
                return True
        else:
            pnl = (entry_price - current_price)
            if pnl > 0 and pnl >= entry_price * take_profit:
                return True
        
        return False
    
    def _adjust_position_python(self, current_price: float, 
                             entry_price: float,
                             direction: int,
                             position_size: float,
                             max_position_size: float,
                             position_adjustment_enabled: bool) -> float:
        """
        Python 版本的仓位调整（备用）
        """
        if not position_adjustment_enabled:
            return position_size
        
        if max_position_size <= 0:
            return position_size
        
        if direction == 1:
            pnl = (current_price - entry_price)
            if pnl > 0:
                new_size = min(position_size * 1.5, max_position_size)
                return new_size
        else:
            pnl = (entry_price - current_price)
            if pnl > 0:
                new_size = min(position_size * 1.5, max_position_size)
                return new_size
        
        return position_size
