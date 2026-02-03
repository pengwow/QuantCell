#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试回测服务的多货币对回测功能
"""

import sys
import os
from pathlib import Path

# 添加项目根目录和backend目录到Python路径
project_root = Path(__file__).parent
sys.path.append(str(project_root))
sys.path.append(str(project_root / "backend"))

# 避免导入routes模块，直接导入service
from backtest.service import BacktestService


def test_multi_currency_backtest():
    """
    测试多货币对回测功能
    """
    print("=== 开始测试多货币对回测功能 ===")
    
    # 创建回测服务实例
    backtest_service = BacktestService()
    
    # 定义测试配置
    strategy_config = {
        "strategy_name": "SMA"
    }
    
    backtest_config = {
        "symbols": ["BTCUSDT", "ETHUSDT"],
        "interval": "1h",
        "start_time": "2024-01-01",
        "end_time": "2024-01-10",
        "initial_cash": 10000,
        "commission": 0.001
    }
    
    try:
        # 执行回测
        result = backtest_service.run_backtest(strategy_config, backtest_config)
        
        print(f"\n回测结果:")
        print(f"  task_id: {result['task_id']}")
        print(f"  状态: {result['status']}")
        print(f"  消息: {result['message']}")
        print(f"  成功货币对: {result['successful_currencies']}")
        print(f"  失败货币对: {result['failed_currencies']}")
        
        print(f"\n回测任务摘要:")
        if 'results' in result and 'summary' in result['results']:
            summary = result['results']['summary']
            print(f"  总货币对数量: {summary['total_currencies']}")
            print(f"  成功货币对数量: {summary['successful_currencies']}")
            print(f"  总交易次数: {summary['total_trades']}")
            print(f"  平均每货币对交易次数: {summary['average_trades_per_currency']}")
            print(f"  总收益率: {summary['total_return']}%")
            print(f"  平均收益率: {summary['average_return']}%")
        
        print("\n=== 测试完成 ===")
        return True
    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_single_currency_backtest():
    """
    测试单货币对回测功能
    """
    print("\n=== 开始测试单货币对回测功能 ===")
    
    # 创建回测服务实例
    backtest_service = BacktestService()
    
    # 定义测试配置
    strategy_config = {
        "strategy_name": "SMA"
    }
    
    backtest_config = {
        "symbols": ["BTCUSDT"],
        "interval": "1h",
        "start_time": "2024-01-01",
        "end_time": "2024-01-10",
        "initial_cash": 10000,
        "commission": 0.001
    }
    
    try:
        # 执行回测
        result = backtest_service.run_backtest(strategy_config, backtest_config)
        
        print(f"\n回测结果:")
        print(f"  task_id: {result['task_id']}")
        print(f"  状态: {result['status']}")
        print(f"  消息: {result['message']}")
        print(f"  成功货币对: {result['successful_currencies']}")
        print(f"  失败货币对: {result['failed_currencies']}")
        
        print("\n=== 测试完成 ===")
        return True
    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    # 测试单货币对回测
    test_single_currency_backtest()
    
    # 测试多货币对回测
    test_multi_currency_backtest()
