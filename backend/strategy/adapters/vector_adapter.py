# 向量回测适配器
# 将 StrategyCore 适配到 VectorEngine

import numpy as np
import pandas as pd
from typing import Dict, Any, Optional
from loguru import logger
from core.vector_engine import VectorEngine
from core.strategy_base import UnifiedStrategyBase


class VectorBacktestAdapter:
    """
    向量回测适配器
    将 UnifiedStrategyBase 适配到 VectorEngine
    """
    
    def __init__(self, strategy: UnifiedStrategyBase):
        """
        初始化适配器
        
        参数：
        - strategy: 策略实例
        """
        self.strategy = strategy
        self.engine = VectorEngine()
        self.results = None
    
    def run_backtest(self, data: Dict[str, pd.DataFrame], 
                    init_cash: float = 100000.0,
                    fees: float = 0.001,
                    slippage: float = 0.0001) -> Dict[str, Any]:
        """
        运行向量回测
        
        参数：
        - data: 多交易对数据字典 {symbol: DataFrame}
        - init_cash: 初始资金
        - fees: 手续费率
        - slippage: 滑点
        
        返回：
        - dict: 回测结果
        """
        results = {}
        
        for symbol, df in data.items():
            logger.info(f"开始回测交易对: {symbol}")
            
            # 初始化策略
            self.strategy.on_init()
            
            # 运行策略获取信号
            signals = self._generate_signals(df)
            
            # 准备价格数组
            price = df['Close'].values.reshape(-1, 1)
            
            # 运行向量回测
            result = self.engine.run_backtest(
                price=price,
                entries=signals['entries'].values.reshape(-1, 1),
                exits=signals['exits'].values.reshape(-1, 1),
                init_cash=init_cash,
                fees=fees,
                slippage=slippage
            )
            
            # 添加交易对信息
            result['symbol'] = symbol
            result['data'] = df
            
            results[symbol] = result
            
            logger.info(f"回测完成: {symbol}, 总盈亏: {result['metrics']['total_pnl']:.2f}, 夏普比率: {result['metrics']['sharpe_ratio']:.4f}")
        
        self.results = results
        return results
    
    def _generate_signals(self, df: pd.DataFrame) -> Dict[str, pd.Series]:
        """
        生成交易信号
        
        参数：
        - df: K线数据
        
        返回：
        - dict: 包含 entries 和 exits 的信号
        """
        # 调用策略的 on_bar 方法生成信号
        entries = pd.Series(False, index=df.index)
        exits = pd.Series(False, index=df.index)
        
        # 遍历每根 K线
        for idx, row in df.iterrows():
            bar = {
                'datetime': idx,
                'open': row['Open'],
                'high': row['High'],
                'low': row['Low'],
                'close': row['Close'],
                'volume': row['Volume']
            }
            
            # 调用策略的 on_bar 方法
            self.strategy.on_bar(bar)
            
            # 检查是否有订单
            if hasattr(self.strategy, 'last_order'):
                order = self.strategy.last_order
                if order['direction'] in ['buy', 'long']:
                    entries[idx] = True
                elif order['direction'] in ['sell', 'short']:
                    exits[idx] = True
        
        return {
            'entries': entries,
            'exits': exits
        }
    
    def optimize_parameters(self, data: Dict[str, pd.DataFrame], 
                       param_ranges: Dict[str, list],
                       metric: str = 'sharpe_ratio') -> Dict[str, Any]:
        """
        参数优化
        
        参数：
        - data: 多交易对数据
        - param_ranges: 参数范围
        - metric: 优化指标
        
        返回：
        - dict: 最优参数组合
        """
        from itertools import product
        
        # 生成参数组合
        param_combinations = list(product(*param_ranges.values()))
        
        best_result = None
        best_score = -float('inf')
        
        total_combinations = len(param_combinations)
        logger.info(f"开始参数优化，总组合数: {total_combinations}")
        
        for idx, params in enumerate(param_combinations):
            param_dict = dict(zip(param_ranges.keys(), params))
            
            # 设置策略参数
            self.strategy.params.update(param_dict)
            
            # 运行回测
            results = self.run_backtest(data)
            
            # 计算平均分数
            scores = [r['metrics'][metric] for r in results.values()]
            avg_score = np.mean(scores)
            
            if avg_score > best_score:
                best_score = avg_score
                best_result = {
                    'params': param_dict,
                    'score': avg_score,
                    'results': results
                }
            
            if (idx + 1) % 10 == 0:
                logger.info(f"参数优化进度: {idx + 1}/{total_combinations}, 当前最优分数: {best_score:.4f}")
        
        logger.info(f"参数优化完成，最优参数: {best_result['params']}, 最优分数: {best_result['score']:.4f}")
        return best_result
    
    def get_equity_curve(self, symbol: str) -> pd.Series:
        """
        获取权益曲线
        
        参数：
        - symbol: 交易对
        
        返回：
        - pd.Series: 权益曲线
        """
        if self.results is None or symbol not in self.results:
            return pd.Series()
        
        result = self.results[symbol]
        positions = result['positions']
        cash = result['cash'][0]
        price = result['data']['Close'].values
        
        # 计算权益曲线
        equity = []
        for i in range(len(positions)):
            equity_value = cash + positions[i, 0] * price[i]
            equity.append(equity_value)
        
        return pd.Series(equity, index=result['data'].index)
    
    def get_trades(self, symbol: str) -> pd.DataFrame:
        """
        获取交易记录
        
        参数：
        - symbol: 交易对
        
        返回：
        - pd.DataFrame: 交易记录
        """
        if self.results is None or symbol not in self.results:
            return pd.DataFrame()
        
        result = self.results[symbol]
        trades = result['trades']
        
        if len(trades) == 0:
            return pd.DataFrame()
        
        return pd.DataFrame(trades.tolist())
    
    def get_summary(self) -> Dict[str, Any]:
        """
        获取回测摘要
        
        返回：
        - dict: 回测摘要
        """
        if self.results is None:
            return {}
        
        summary = {
            'symbols': list(self.results.keys()),
            'total_trades': 0,
            'total_pnl': 0.0,
            'total_fees': 0.0,
            'avg_sharpe': 0.0,
            'avg_win_rate': 0.0
        }
        
        for result in self.results.values():
            metrics = result['metrics']
            summary['total_trades'] += metrics['trade_count']
            summary['total_pnl'] += metrics['total_pnl']
            summary['total_fees'] += metrics['total_fees']
            summary['avg_sharpe'] += metrics['sharpe_ratio']
            summary['avg_win_rate'] += metrics['win_rate']
        
        n_symbols = len(self.results)
        if n_symbols > 0:
            summary['avg_sharpe'] /= n_symbols
            summary['avg_win_rate'] /= n_symbols
        
        return summary
