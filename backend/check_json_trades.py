#!/usr/bin/env python3
"""检查JSON文件中的交易记录"""

import json

with open('backtest/results/sma_cross_strategy_20260207_195733_results.json', 'r') as f:
    data = json.load(f)

if 'portfolio' in data:
    trades = data['portfolio'].get('trades', [])
    print(f'总交易数: {len(trades)}')
    
    if trades:
        print('\n第一条交易记录:')
        print(json.dumps(trades[0], indent=2))
        
        print('\n最后一条交易记录:')
        print(json.dumps(trades[-1], indent=2))
        
        # 统计有size字段的交易
        with_size = [t for t in trades if 'size' in t]
        print(f'\n有size字段的交易数: {len(with_size)}')
        
        # 统计有symbol字段的交易
        with_symbol = [t for t in trades if t.get('symbol') is not None]
        print(f'有symbol字段的交易数: {len(with_symbol)}')
