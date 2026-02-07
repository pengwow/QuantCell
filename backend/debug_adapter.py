#!/usr/bin/env python3
"""调试投资组合适配器的交易记录"""

import sys
sys.path.insert(0, '/Users/liupeng/workspace/quant/QuantCell/backend')

from strategy.adapters.portfolio_adapter import PortfolioBacktestAdapter
import pandas as pd
import numpy as np

# 创建模拟数据
np.random.seed(42)
dates = pd.date_range('2024-01-01', periods=100, freq='1h')

# 创建两个交易对的模拟数据
data = {
    'BTCUSDT_1h': pd.DataFrame({
        'Open': 100 + np.random.randn(100).cumsum(),
        'High': 101 + np.random.randn(100).cumsum(),
        'Low': 99 + np.random.randn(100).cumsum(),
        'Close': 100 + np.random.randn(100).cumsum(),
        'Volume': np.random.randint(1000, 10000, 100)
    }, index=dates),
    'ETHUSDT_1h': pd.DataFrame({
        'Open': 50 + np.random.randn(100).cumsum(),
        'High': 51 + np.random.randn(100).cumsum(),
        'Low': 49 + np.random.randn(100).cumsum(),
        'Close': 50 + np.random.randn(100).cumsum(),
        'Volume': np.random.randint(500, 5000, 100)
    }, index=dates)
}

# 创建适配器
class MockStrategy:
    def on_bar(self, bar_data):
        # 简单的随机信号
        import random
        if random.random() > 0.7:
            return {'entry': True, 'exit': False}
        elif random.random() > 0.7:
            return {'entry': False, 'exit': True}
        return {'entry': False, 'exit': False}

adapter = PortfolioBacktestAdapter(MockStrategy())

# 运行回测
results = adapter.run(data, init_cash=100000.0)

# 检查交易记录
print("=== 检查交易记录 ===")
if 'portfolio' in results:
    trades = results['portfolio'].get('trades', [])
    print(f"总交易数: {len(trades)}")
    if trades:
        print("\n前5条交易记录:")
        for i, t in enumerate(trades[:5]):
            print(f"  {i+1}. symbol={repr(t.get('symbol'))}, pnl={t.get('pnl')}, direction={t.get('direction')}")

# 检查序列化后的结果
from backtest.result_analysis import BacktestResultManager
manager = BacktestResultManager()
serialized = manager._make_serializable(results)

print("\n=== 检查序列化后的交易记录 ===")
if 'portfolio' in serialized:
    trades = serialized['portfolio'].get('trades', [])
    print(f"总交易数: {len(trades)}")
    if trades:
        print("\n前5条交易记录:")
        for i, t in enumerate(trades[:5]):
            print(f"  {i+1}. symbol={repr(t.get('symbol'))}, pnl={t.get('pnl')}, direction={t.get('direction')}")
