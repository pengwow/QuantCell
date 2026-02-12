#!/usr/bin/env python3
"""
QuantCell 框架性能测试
"""

import sys
from pathlib import Path
from typing import Dict
import pandas as pd
import time

# 添加backend到路径
backend_path = Path(__file__).resolve().parent.parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from scripts.performance_test.base_test import BasePerformanceTest, Timer


class QuantCellPerformanceTest(BasePerformanceTest):
    """QuantCell 框架性能测试"""
    
    def __init__(self):
        super().__init__("QuantCell")
        
    def load_data(self, data_file: str) -> pd.DataFrame:
        """加载数据"""
        # 使用与 validate_strategy.py 相同的数据加载逻辑
        from scripts.validate_strategy import load_and_normalize_data
        return load_and_normalize_data(data_file)
        
    def run_strategy(self, data: pd.DataFrame, strategy_params: Dict) -> Dict:
        """执行策略"""
        # 导入策略
        from strategies.sma_crossover_quantcell import SmaCrossOverQuantCell
        
        # 创建策略实例
        strategy = SmaCrossOverQuantCell(strategy_params)
        
        # 测量信号生成时间
        with Timer() as signal_timer:
            # 计算指标
            indicators = strategy.calculate_indicators(data)
            
            # 生成信号
            signals = strategy.generate_signals(indicators)
            entries = signals.get('entries', pd.Series(False, index=data.index))
            exits = signals.get('exits', pd.Series(False, index=data.index))
        
        # 将信号转换为统一格式
        signal_series = pd.Series(0, index=data.index)
        signal_series[entries] = 1
        signal_series[exits] = -1
        
        # 模拟交易执行
        trades = self._simulate_trades(data, signal_series)
        
        return {
            'total_trades': len(trades),
            'signals_generated': entries.sum() + exits.sum(),
            'signal_latency_ms': signal_timer.elapsed_ms,
        }
        
    def _simulate_trades(self, data: pd.DataFrame, signals: pd.Series) -> list:
        """简化的交易模拟"""
        trades = []
        position = 0
        
        for timestamp, row in data.iterrows():
            signal = signals.loc[timestamp]
            
            if signal == 1 and position == 0:
                position = 1
                trades.append({
                    'entry_time': timestamp,
                    'entry_price': row['Close'],
                    'side': 'long'
                })
            elif signal == -1 and position > 0:
                position = 0
                if trades:
                    trades[-1]['exit_time'] = timestamp
                    trades[-1]['exit_price'] = row['Close']
                    
        return [t for t in trades if 'exit_time' in t]
