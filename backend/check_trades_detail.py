#!/usr/bin/env python3
import json
with open('backtest/results/sma_cross_strategy_20260207_195733_results.json', 'r') as f:
    data = json.load(f)

if 'portfolio' in data:
    trades = data['portfolio'].get('trades', [])
    print(f'总交易数: {len(trades)}')
    if trades:
        print('\n前5条交易记录:')
        for i, t in enumerate(trades[:5]):
            print(f'  {i+1}. symbol={t.get("symbol")}, pnl={t.get("pnl")}, direction={t.get("direction")}')

        # 统计有pnl的交易
        trades_with_pnl = [t for t in trades if 'pnl' in t and t.get('pnl') is not None]
        print(f'\n有pnl的交易数: {len(trades_with_pnl)}')

        # 按symbol统计
        from collections import Counter
        symbol_counts = Counter(t.get('symbol') for t in trades if t.get('symbol'))
        print(f'\n按symbol统计交易数:')
        for sym, count in symbol_counts.items():
            print(f'  {sym}: {count}')

        # 按symbol统计有pnl的交易
        symbol_pnl_counts = Counter(t.get('symbol') for t in trades_with_pnl if t.get('symbol'))
        print(f'\n按symbol统计有pnl的交易数:')
        for sym, count in symbol_pnl_counts.items():
            print(f'  {sym}: {count}')
