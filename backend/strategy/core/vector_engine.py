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
        
        # 尝试导入 Numba 编译函数
        try:
            from .numba_functions import (
                simulate_orders,
                signals_to_orders,
                calculate_metrics,
                calculate_funding_rate,
                calculate_funding_payment
            )
            
            self.simulate_orders = simulate_orders
            self.signals_to_orders = signals_to_orders
            self.calculate_metrics = calculate_metrics
            self.calculate_funding_rate = calculate_funding_rate
            self.calculate_funding_payment = calculate_funding_payment
            
            logger.info("使用 Numba JIT 编译模块（高性能模式）")
        except ImportError as e:
            # 如果 Numba 未安装，使用 Python 实现
            self.simulate_orders = self._simulate_orders_python
            self.signals_to_orders = self._signals_to_orders_python
            self.calculate_metrics = self._calculate_metrics_python
            self.calculate_funding_rate = self._calculate_funding_rate_python
            self.calculate_funding_payment = self._calculate_funding_payment_python
            
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
        """
        n_steps, n_assets = price.shape
        
        # 初始化状态
        cash = np.full(n_assets, init_cash, dtype=np.float64)
        positions = np.zeros((n_steps, n_assets), dtype=np.float64)
        
        # 遍历每个时间步
        for i in range(n_steps):
            for j in range(n_assets):
                # 获取当前价格
                current_price = price[i, j]
                
                # 检查是否有订单
                if size[i, j] != 0:
                    if direction[i, j] == 1:  # long
                        exec_price = current_price * (1 + slippage)
                        req_cash = size[i, j] * exec_price * (1 + fees)
                        
                        if cash[j] >= req_cash:
                            cash[j] -= req_cash
                            positions[i, j] += size[i, j]
                    else:  # short
                        exec_price = current_price * (1 - slippage)
                        req_cash = size[i, j] * exec_price * (1 + fees)
                        
                        if positions[i, j] >= size[i, j]:
                            cash[j] += req_cash
                            positions[i, j] -= size[i, j]
        
        return cash, positions
    
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
        
        return {
            'total_pnl': float(total_pnl),
            'total_fees': float(total_fees),
            'win_rate': float(win_rate),
            'sharpe_ratio': float(sharpe_ratio),
            'trade_count': len(trades),
            'final_equity': float(cash.sum())
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
