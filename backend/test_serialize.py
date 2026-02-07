#!/usr/bin/env python3
"""测试序列化过程"""

import sys
sys.path.insert(0, '/Users/liupeng/workspace/quant/QuantCell/backend')

from backtest.result_analysis import ResultSerializer
import pandas as pd
from datetime import datetime

# 创建模拟交易数据
trades = [
    {
        'symbol': 'BTC/USDT_15m',
        'direction': 'buy',
        'size': 1.0,
        'price': 50000.0,
        'timestamp': pd.Timestamp('2024-01-01 00:00:00'),
        'cost': 50000.0,
        'fees': 50.0
    },
    {
        'symbol': 'BTC/USDT_15m',
        'direction': 'sell',
        'size': 1.0,
        'price': 51000.0,
        'timestamp': pd.Timestamp('2024-01-02 00:00:00'),
        'revenue': 50949.0,
        'pnl': 949.0,
        'fees': 51.0,
        'entry_price': 50000.0,
        'entry_time': pd.Timestamp('2024-01-01 00:00:00')
    }
]

print("原始交易记录:")
for i, t in enumerate(trades):
    print(f"  {i+1}. symbol={repr(t.get('symbol'))}, pnl={t.get('pnl')}")

# 序列化
serializer = ResultSerializer()
serialized = serializer._serialize_orders(trades)

print("\n序列化后的交易记录:")
for i, t in enumerate(serialized):
    print(f"  {i+1}. symbol={repr(t.get('symbol'))}, pnl={t.get('pnl')}")
    print(f"     所有键: {list(t.keys())}")
