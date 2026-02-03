#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试多货币对回测场景
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.append(str(project_root))
sys.path.append(str(project_root / "backend"))

# 只测试service.py的核心逻辑，避免导入routes等模块
from backtest.service import BacktestService


def test_multi_currency_backtest():
    """
    测试多货币对回测场景
    """
    print("=== 开始测试多货币对回测场景 ===")
    
    # 创建回测服务实例
    backtest_service = BacktestService()
    
    # 定义测试配置
    strategy_config = {
        "strategy_name": "SMA"
    }
    
    backtest_config = {
        "symbols": ["BTCUSDT", "ETHUSDT"],  # 多货币对
        "interval": "1h",
        "start_time": "2024-01-01",
        "end_time": "2024-01-10",
        "initial_cash": 10000,
        "commission": 0.001
    }
    
    try:
        # 执行回测
        result = backtest_service.run_backtest(strategy_config, backtest_config)
        
        print(f"回测结果状态: {result['status']}")
        print(f"task_id: {result['task_id']}")
        print(f"消息: {result['message']}")
        print(f"成功货币对: {result['successful_currencies']}")
        print(f"失败货币对: {result['failed_currencies']}")
        
        # 检查结果结构
        assert 'task_id' in result, "缺少task_id字段"
        assert 'status' in result, "缺少status字段"
        assert 'successful_currencies' in result, "缺少successful_currencies字段"
        assert 'failed_currencies' in result, "缺少failed_currencies字段"
        assert 'results' in result, "缺少results字段"
        
        # 检查总货币对数量
        assert len(result['successful_currencies']) + len(result['failed_currencies']) == 2, f"期望2个货币对，实际{len(result['successful_currencies']) + len(result['failed_currencies'])}个"
        
        # 检查所有货币对都被处理
        all_currencies = set(result['successful_currencies'] + result['failed_currencies'])
        assert all_currencies == set(["BTCUSDT", "ETHUSDT"]), f"期望处理的货币对为BTCUSDT和ETHUSDT，实际{all_currencies}"
        
        print("\n=== 测试通过 ===")
        return True
    except Exception as e:
        print(f"\n=== 测试失败 ===")
        print(f"错误信息: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    test_multi_currency_backtest()
