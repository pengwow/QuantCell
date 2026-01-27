#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试单货币对回测场景
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.append(str(project_root))
sys.path.append(str(project_root / "backend"))

# 只测试service.py的核心逻辑，避免导入routes等模块
from backend.backtest.service import BacktestService


def test_single_currency_backtest():
    """
    测试单货币对回测场景
    """
    print("=== 开始测试单货币对回测场景 ===")
    
    # 创建回测服务实例
    backtest_service = BacktestService()
    
    # 定义测试配置
    strategy_config = {
        "strategy_name": "SMA"
    }
    
    backtest_config = {
        "symbols": ["BTCUSDT"],  # 单货币对
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
        
        # 检查成功货币对数量
        assert len(result['successful_currencies']) == 1, f"期望1个成功货币对，实际{len(result['successful_currencies'])}个"
        assert result['successful_currencies'][0] == "BTCUSDT", f"期望成功货币对为BTCUSDT，实际{result['successful_currencies'][0]}"
        
        # 检查失败货币对数量
        assert len(result['failed_currencies']) == 0, f"期望0个失败货币对，实际{len(result['failed_currencies'])}个"
        
        print("\n=== 测试通过 ===")
        return True
    except Exception as e:
        print(f"\n=== 测试失败 ===")
        print(f"错误信息: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    test_single_currency_backtest()
