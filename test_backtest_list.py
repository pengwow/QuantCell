#!/usr/bin/env python3
# 测试回测任务列表API

import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.append(str(project_root))

# 直接导入BacktestService，避免导入__init__.py中的routes模块
sys.path.append(str(project_root / "backend"))
from backtest.service import BacktestService

# 创建回测服务实例
service = BacktestService()

# 测试list_backtest_results方法
print("测试list_backtest_results方法...")
backtest_list = service.list_backtest_results()

print(f"\n回测任务列表长度: {len(backtest_list)}")
print("\n回测任务详情:")
for i, task in enumerate(backtest_list[:5]):  # 只显示前5个任务
    print(f"\n任务 {i+1}:")
    print(f"  ID: {task.get('id')}")
    print(f"  策略名称: {task.get('strategy_name')}")
    print(f"  创建时间: {task.get('created_at')}")
    print(f"  状态: {task.get('status')}")
    print(f"  总收益率: {task.get('total_return', 'N/A')}")
    print(f"  最大回撤: {task.get('max_drawdown', 'N/A')}")

print("\n测试完成!")
