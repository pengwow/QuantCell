#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试多货币对回测结果合并功能
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.append(str(project_root))
sys.path.append(str(project_root / "backend"))

from backend.backtest.service import BacktestService


def test_merge_backtest_results():
    """
    测试多货币对回测结果合并功能
    """
    print("=== 开始测试多货币对回测结果合并功能 ===")
    
    # 创建回测服务实例
    backtest_service = BacktestService()
    
    # 创建模拟的回测结果
    mock_results = {
        "BTCUSDT": {
            "id": "1",
            "symbol": "BTCUSDT",
            "task_id": "task1",
            "status": "success",
            "strategy_name": "SMA",
            "backtest_config": {
                "symbol": "BTCUSDT",
                "initial_cash": 10000
            },
            "metrics": [
                {"name": "Return [%]", "value": 10.5},
                {"name": "Max. Drawdown [%]", "value": 5.2},
                {"name": "Sharpe Ratio", "value": 1.8},
                {"name": "Equity Final [$]", "value": 11050}
            ],
            "trades": [
                {"EntryTime": "2024-01-01", "Direction": "多单", "EntryPrice": 40000},
                {"EntryTime": "2024-01-02", "Direction": "空单", "EntryPrice": 42000}
            ],
            "equity_curve": [],
            "strategy_data": []
        },
        "ETHUSDT": {
            "id": "2",
            "symbol": "ETHUSDT",
            "task_id": "task1",
            "status": "success",
            "strategy_name": "SMA",
            "backtest_config": {
                "symbol": "ETHUSDT",
                "initial_cash": 10000
            },
            "metrics": [
                {"name": "Return [%]", "value": 8.2},
                {"name": "Max. Drawdown [%]", "value": 3.8},
                {"name": "Sharpe Ratio", "value": 1.5},
                {"name": "Equity Final [$]", "value": 10820}
            ],
            "trades": [
                {"EntryTime": "2024-01-01", "Direction": "多单", "EntryPrice": 3000},
                {"EntryTime": "2024-01-02", "Direction": "多单", "EntryPrice": 3100},
                {"EntryTime": "2024-01-03", "Direction": "空单", "EntryPrice": 3200}
            ],
            "equity_curve": [],
            "strategy_data": []
        },
        "BNBUSDT": {
            "id": "3",
            "symbol": "BNBUSDT",
            "task_id": "task1",
            "status": "failed",
            "message": "数据获取失败",
            "strategy_name": "SMA",
            "backtest_config": {
                "symbol": "BNBUSDT",
                "initial_cash": 10000
            },
            "metrics": [],
            "trades": [],
            "equity_curve": [],
            "strategy_data": []
        }
    }
    
    try:
        # 测试合并结果方法
        merged_result = backtest_service.merge_backtest_results(mock_results)
        
        print(f"\n合并结果状态: {merged_result['status']}")
        print(f"成功货币对: {merged_result['successful_currencies']}")
        print(f"失败货币对: {merged_result['failed_currencies']}")
        
        if 'summary' in merged_result:
            summary = merged_result['summary']
            print(f"\n合并结果摘要:")
            print(f"  总货币对数量: {summary['total_currencies']}")
            print(f"  成功货币对数量: {summary['successful_currencies']}")
            print(f"  失败货币对数量: {summary['failed_currencies']}")
            print(f"  总交易次数: {summary['total_trades']}")
            print(f"  平均每货币对交易次数: {summary['average_trades_per_currency']}")
            print(f"  总初始资金: {summary['total_initial_cash']}")
            print(f"  总权益: {summary['total_equity']}")
            print(f"  总收益率: {summary['total_return']}%")
            print(f"  平均收益率: {summary['average_return']}%")
            print(f"  平均最大回撤: {summary['average_max_drawdown']}%")
            print(f"  平均夏普比率: {summary['average_sharpe_ratio']}")
        
        # 验证合并结果
        assert merged_result['status'] == 'success', "合并结果状态应该为success"
        assert len(merged_result['successful_currencies']) == 2, "应该有2个成功货币对"
        assert len(merged_result['failed_currencies']) == 1, "应该有1个失败货币对"
        assert set(merged_result['successful_currencies']) == set(["BTCUSDT", "ETHUSDT"]), "成功货币对应该是BTCUSDT和ETHUSDT"
        assert set(merged_result['failed_currencies']) == set(["BNBUSDT"]), "失败货币对应该是BNBUSDT"
        
        if 'summary' in merged_result:
            summary = merged_result['summary']
            assert summary['total_currencies'] == 3, "总货币对数量应该是3"
            assert summary['successful_currencies'] == 2, "成功货币对数量应该是2"
            assert summary['failed_currencies'] == 1, "失败货币对数量应该是1"
            assert summary['total_trades'] == 5, "总交易次数应该是5"
            assert summary['total_initial_cash'] == 20000, "总初始资金应该是20000"
            assert summary['total_equity'] == 21870, "总权益应该是21870"
            assert abs(summary['total_return'] - 9.35) < 0.01, "总收益率应该约为9.35%"
        
        print("\n=== 测试通过 ===")
        return True
    except Exception as e:
        print(f"\n=== 测试失败 ===")
        print(f"错误信息: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    test_merge_backtest_results()
