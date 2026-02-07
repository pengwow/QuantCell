#!/usr/bin/env python3
"""调试序列化过程"""

import json

# 读取原始结果文件
with open('backtest/results/sma_cross_strategy_20260207_195733_results.json', 'r') as f:
    data = json.load(f)

# 检查portfolio中的trades
if 'portfolio' in data:
    trades = data['portfolio'].get('trades', [])
    print(f"总交易数: {len(trades)}")
    
    # 检查第一条交易的完整内容
    if trades:
        print("\n第一条交易的完整内容:")
        print(json.dumps(trades[0], indent=2, default=str))
        
    # 统计有多少交易有symbol字段
    with_symbol = [t for t in trades if t.get('symbol') is not None]
    print(f"\n有symbol的交易数: {len(with_symbol)}")
    
    # 统计有多少交易有pnl字段
    with_pnl = [t for t in trades if t.get('pnl') is not None]
    print(f"有pnl的交易数: {len(with_pnl)}")
