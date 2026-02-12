#!/usr/bin/env python3
"""
Freqtrade 框架性能测试
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


class FreqtradePerformanceTest(BasePerformanceTest):
    """Freqtrade 框架性能测试"""

    def __init__(self):
        super().__init__("Freqtrade")

    def load_data(self, data_file: str) -> pd.DataFrame:
        """加载数据"""
        from scripts.validate_strategy import load_and_normalize_data
        return load_and_normalize_data(data_file)

    def run_strategy(self, data: pd.DataFrame, strategy_params: Dict) -> Dict:
        """执行策略"""
        fast_period = strategy_params.get('fast', 10)
        slow_period = strategy_params.get('slow', 30)

        with Timer() as timer:
            # 计算SMA指标
            sma_fast = data['Close'].rolling(window=fast_period).mean()
            sma_slow = data['Close'].rolling(window=slow_period).mean()

            # 生成信号
            buy_signals = (sma_fast > sma_slow) & (sma_fast.shift(1) <= sma_slow.shift(1))
            sell_signals = (sma_fast < sma_slow) & (sma_fast.shift(1) >= sma_slow.shift(1))

            # 模拟交易
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
