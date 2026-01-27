#!/usr/bin/env python3
# 测试回测结果保存和加载功能

import json
import os
import sys
from pathlib import Path

def test_backtest_result_save_load():
    """测试回测结果保存和加载功能"""
    print("=== 测试回测结果保存和加载功能 ===")
    
    # 模拟合并后的回测结果
    mock_merged_result = {
        "task_id": "test_task_id",
        "status": "success",
        "message": "多货币对回测完成",
        "strategy_name": "TestStrategy",
        "backtest_config": {"initial_cash": 10000},
        "summary": {
            "total_currencies": 2,
            "successful_currencies": 2,
            "failed_currencies": 0,
            "total_trades": 0,
            "average_trades_per_currency": 0,
            "total_initial_cash": 20000,
            "total_equity": 23000,
            "total_return": 15,
            "average_return": 15,
            "average_max_drawdown": 6.5,
            "average_sharpe_ratio": 1.75,
            "average_sortino_ratio": 0,
            "average_calmar_ratio": 0,
            "average_win_rate": 0,
            "average_profit_factor": 0
        },
        "currencies": {
            "BTCUSDT": {
                "status": "success",
                "equity_curve": [
                    {"datetime": "2023-01-01", "Equity": 10000},
                    {"datetime": "2023-01-02", "Equity": 10100},
                    {"datetime": "2023-01-03", "Equity": 11000},
                ]
            },
            "ETHUSDT": {
                "status": "success",
                "equity_curve": [
                    {"datetime": "2023-01-01", "Equity": 10000},
                    {"datetime": "2023-01-02", "Equity": 10500},
                    {"datetime": "2023-01-03", "Equity": 12000},
                ]
            }
        },
        "merged_equity_curve": [
            {"datetime": "2023-01-01", "Equity": 20000},
            {"datetime": "2023-01-02", "Equity": 20600},
            {"datetime": "2023-01-03", "Equity": 23000},
        ],
        "successful_currencies": ["BTCUSDT", "ETHUSDT"],
        "failed_currencies": []
    }
    
    print("模拟合并后的回测结果:")
    print(f"合并资金曲线长度: {len(mock_merged_result.get('merged_equity_curve', []))}")
    
    # 模拟保存回测结果到文件系统
    backtest_result_dir = Path(".") / "backend" / "backtest" / "results"
    backtest_result_dir.mkdir(parents=True, exist_ok=True)
    
    result_path = backtest_result_dir / f"{mock_merged_result['task_id']}.json"
    
    print(f"\n保存回测结果到文件: {result_path}")
    
    try:
        with open(result_path, "w") as f:
            json.dump(mock_merged_result, f, indent=4, default=str, ensure_ascii=False)
        print("✅ 回测结果保存成功")
    except Exception as e:
        print(f"❌ 回测结果保存失败: {e}")
        return False
    
    # 模拟加载回测结果
    print(f"\n从文件加载回测结果: {result_path}")
    
    try:
        with open(result_path, "r", encoding="utf-8") as f:
            loaded_result = json.load(f)
        print("✅ 回测结果加载成功")
    except Exception as e:
        print(f"❌ 回测结果加载失败: {e}")
        return False
    
    # 验证加载的结果
    print("\n验证加载的结果:")
    print(f"状态: {loaded_result.get('status')}")
    print(f"成功货币对数量: {len(loaded_result.get('successful_currencies', []))}")
    print(f"合并资金曲线长度: {len(loaded_result.get('merged_equity_curve', []))}")
    
    merged_equity_curve = loaded_result.get('merged_equity_curve', [])
    if not merged_equity_curve:
        print("❌ 测试失败: 合并资金曲线为空")
        return False
    elif len(merged_equity_curve) != 3:
        print(f"❌ 测试失败: 合并资金曲线长度不正确，期望3，实际{len(merged_equity_curve)}")
        return False
    elif merged_equity_curve[0]["Equity"] != 20000:
        print(f"❌ 测试失败: 第一个时间点的权益值不正确，期望20000，实际{merged_equity_curve[0]['Equity']}")
        return False
    elif merged_equity_curve[1]["Equity"] != 20600:
        print(f"❌ 测试失败: 第二个时间点的权益值不正确，期望20600，实际{merged_equity_curve[1]['Equity']}")
        return False
    elif merged_equity_curve[2]["Equity"] != 23000:
        print(f"❌ 测试失败: 第三个时间点的权益值不正确，期望23000，实际{merged_equity_curve[2]['Equity']}")
        return False
    else:
        print("✅ 测试成功: 回测结果保存和加载功能正常")
        return True

if __name__ == "__main__":
    # 运行测试
    test_passed = test_backtest_result_save_load()
    
    if test_passed:
        print("\n🎉 测试通过！")
        sys.exit(0)
    else:
        print("\n❌ 测试失败！")
        sys.exit(1)
