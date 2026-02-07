#!/usr/bin/env python3
import json
with open('backtest/results/sma_cross_strategy_20260207_195733_results.json', 'r') as f:
    data = json.load(f)

print('顶层键:', list(data.keys()))

if 'portfolio' in data:
    trades = data['portfolio'].get('trades', [])
    print(f'\n总交易数: {len(trades)}')

    # 检查前10条交易的symbol字段
    print('\n前10条交易的symbol字段:')
    for i, t in enumerate(trades[:10]):
        symbol = t.get('symbol')
        print(f'  {i+1}. symbol={repr(symbol)}, type={type(symbol).__name__}')

    # 检查所有非None的symbol
    non_none_symbols = [t.get('symbol') for t in trades if t.get('symbol') is not None]
    print(f'\n非None的symbol数量: {len(non_none_symbols)}')
    if non_none_symbols:
        print(f'示例: {non_none_symbols[:5]}')
