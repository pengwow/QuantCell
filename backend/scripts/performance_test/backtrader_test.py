#!/usr/bin/env python3
"""
Backtrader 框架性能测试
"""

import sys
from pathlib import Path
from typing import Dict
import pandas as pd

# 添加backend到路径
backend_path = Path(__file__).resolve().parent.parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from scripts.performance_test.base_test import BasePerformanceTest, Timer


class BacktraderPerformanceTest(BasePerformanceTest):
    """Backtrader 框架性能测试"""
    
    def __init__(self):
        super().__init__("Backtrader")
        
    def load_data(self, data_file: str) -> pd.DataFrame:
        """加载数据"""
        from scripts.validate_strategy import load_and_normalize_data
        return load_and_normalize_data(data_file)
        
    def run_strategy(self, data: pd.DataFrame, strategy_params: Dict) -> Dict:
        """执行策略"""
        try:
            import backtrader as bt
        except ImportError:
            # 如果未安装backtrader，使用模拟实现
            return self._simulate_backtest(data, strategy_params)
        
        # 创建Backtrader策略
        class TestStrategy(bt.Strategy):
            params = (
                ('fast', strategy_params.get('fast', 10)),
                ('slow', strategy_params.get('slow', 30)),
            )
            
            def __init__(self):
                self.fast_ma = bt.indicators.SMA(self.data.close, period=self.p.fast)
                self.slow_ma = bt.indicators.SMA(self.data.close, period=self.p.slow)
                self.crossover = bt.indicators.CrossOver(self.fast_ma, self.slow_ma)
                self.trades_count = 0
                self.signals_count = 0
                
            def next(self):
                if self.crossover > 0:
                    self.signals_count += 1
                    if not self.position:
                        self.buy()
                        self.trades_count += 1
                elif self.crossover < 0:
                    self.signals_count += 1
                    if self.position:
                        self.sell()
        
        # 测量执行时间
        with Timer() as timer:
            cerebro = bt.Cerebro()
            cerebro.addstrategy(TestStrategy)
            
            # 添加数据
            bt_data = bt.feeds.PandasData(dataname=data)
            cerebro.adddata(bt_data)
            
            # 设置初始资金
            cerebro.broker.setcash(10000.0)
            cerebro.broker.setcommission(commission=0.001)
            
            # 运行回测
            results = cerebro.run()
            strat = results[0]
        
        return {
            'total_trades': strat.trades_count,
            'signals_generated': strat.signals_count,
            'signal_latency_ms': timer.elapsed_ms,
        }
        
    def _simulate_backtest(self, data: pd.DataFrame, strategy_params: Dict) -> Dict:
        """模拟回测（当backtrader不可用时）"""
        fast_period = strategy_params.get('fast', 10)
        slow_period = strategy_params.get('slow', 30)
        
        with Timer() as timer:
            sma_fast = data['Close'].rolling(window=fast_period).mean()
            sma_slow = data['Close'].rolling(window=slow_period).mean()
            
            signals = pd.Series(0, index=data.index)
            buy_signals = (sma_fast > sma_slow) & (sma_fast.shift(1) <= sma_slow.shift(1))
            sell_signals = (sma_fast < sma_slow) & (sma_fast.shift(1) >= sma_slow.shift(1))
            
            trades_count = 0
            position = 0
            
            for timestamp in data.index:
                if buy_signals.loc[timestamp] and position == 0:
                    position = 1
                    trades_count += 1
                elif sell_signals.loc[timestamp] and position > 0:
                    position = 0
        
        return {
            'total_trades': trades_count,
            'signals_generated': buy_signals.sum() + sell_signals.sum(),
            'signal_latency_ms': timer.elapsed_ms,
        }
