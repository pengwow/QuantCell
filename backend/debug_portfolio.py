#!/usr/bin/env python3
"""调试portfolio结果的序列化"""

import json

# 读取原始结果文件
with open('backtest/results/sma_cross_strategy_20260207_195733_results.json', 'r') as f:
    data = json.load(f)

# 检查portfolio的结构
if 'portfolio' in data:
    portfolio = data['portfolio']
    print("portfolio的键:", list(portfolio.keys()))

    # 检查trades字段
    if 'trades' in portfolio:
        trades = portfolio['trades']
        print(f"\ntrades数量: {len(trades)}")
        if trades:
            print("\n第一条trade的键:", list(trades[0].keys()))
            print("第一条trade:", json.dumps(trades[0], indent=2))

    # 检查原始数据（从JSON加载的）
    print("\n=== JSON中的原始数据 ===")
    portfolio_data = data['portfolio']
    print(f"portfolio_data类型: {type(portfolio_data)}")
    print(f"portfolio_data键: {list(portfolio_data.keys())}")

    # 检查trades字段的类型
    if 'trades' in portfolio_data:
        trades = portfolio_data['trades']
        print(f"\ntrades类型: {type(trades)}")
        print(f"trades长度: {len(trades)}")
        if trades:
            print(f"第一条trade类型: {type(trades[0])}")
            print(f"第一条trade: {trades[0]}")
