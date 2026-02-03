#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简单测试回测服务的核心功能
"""

import sys
import os
from pathlib import Path
import json

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.append(str(project_root))
sys.path.append(str(project_root / "backend"))

# 只测试service.py的核心逻辑，避免导入routes等模块
from backtest.service import BacktestService


def test_run_single_backtest():
    """
    测试单个货币对回测
    """
    print("=== 测试单个货币对回测 ===")
    
    # 创建回测服务实例
    backtest_service = BacktestService()
    
    # 定义测试配置
    strategy_config = {
        "strategy_name": "SMA"
    }
    
    backtest_config = {
        "symbol": "BTCUSDT",
        "interval": "1h",
        "start_time": "2024-01-01",
        "end_time": "2024-01-10",
        "initial_cash": 10000,
        "commission": 0.001
    }
    
    # 生成task_id
    import uuid
    task_id = str(uuid.uuid4())
    
    try:
        # 测试run_single_backtest方法
        result = backtest_service.run_single_backtest(strategy_config, backtest_config, task_id)
        
        print(f"回测结果: {result['status']}")
        print(f"货币对: {result['symbol']}")
        print(f"task_id: {result['task_id']}")
        
        return True
    except Exception as e:
        print(f"测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_merge_results():
    """
    测试合并回测结果
    """
    print("\n=== 测试合并回测结果 ===")
    
    # 创建模拟的回测结果
    results = {
        "BTCUSDT": {
            "id": "1",
            "symbol": "BTCUSDT",
            "task_id": "task1",
            "status": "success",
            "metrics": [{"name": "Return [%]", "value": 10.5}],
            "trades": [],
            "equity_curve": [],
            "strategy_data": []
        },
        "ETHUSDT": {
            "id": "2",
            "symbol": "ETHUSDT",
            "task_id": "task1",
            "status": "success",
            "metrics": [{"name": "Return [%]", "value": 8.2}],
            "trades": [],
            "equity_curve": [],
            "strategy_data": []
        }
    }
    
    # 创建回测服务实例
    backtest_service = BacktestService()
    
    try:
        # 测试合并结果方法
        merged_result = backtest_service.merge_backtest_results(results)
        
        print(f"合并结果状态: {merged_result['status']}")
        print(f"成功货币对: {merged_result['successful_currencies']}")
        print(f"总收益率: {merged_result['summary']['total_return']}%")
        
        return True
    except Exception as e:
        print(f"测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    # 测试单个回测
    # test_run_single_backtest()
    
    # 测试结果合并
    test_merge_results()
