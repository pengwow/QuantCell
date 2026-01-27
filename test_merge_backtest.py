#!/usr/bin/env python3
# 测试回测结果合并逻辑

import sys
import os
import json
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.append(str(project_root))

# 回测结果文件目录
backtest_result_dir = project_root / "backend" / "backtest" / "results"

# 测试任务ID
test_task_id = "5068f2ad-11d8-4921-988a-0a0167ea56aa"

# 测试加载回测结果文件
def load_backtest_result(task_id):
    result_path = backtest_result_dir / f"{task_id}.json"
    if not result_path.exists():
        print(f"错误: 回测结果文件不存在")
        return None
    
    try:
        with open(result_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"错误: 加载文件失败 - {e}")
        return None

# 测试合并回测结果逻辑
def test_merge_logic():
    print("测试回测结果合并逻辑...")
    
    # 加载回测结果
    backtest_result = load_backtest_result(test_task_id)
    if not backtest_result:
        return
    
    print(f"\n回测结果类型: {'多货币对' if 'currencies' in backtest_result else '单货币对'}")
    
    # 检查currencies部分
    if "currencies" in backtest_result:
        print(f"\n货币对数量: {len(backtest_result['currencies'])}")
        
        # 遍历每个货币对
        for symbol, currency_result in backtest_result['currencies'].items():
            print(f"\n货币对: {symbol}")
            print(f"  状态: {currency_result.get('status')}")
            
            # 检查metrics部分
            if "metrics" in currency_result:
                print(f"  指标数量: {len(currency_result['metrics'])}")
                
                # 查找最终权益和总收益率指标
                equity_final = None
                total_return = None
                
                for metric in currency_result['metrics']:
                    metric_key = metric.get("key", metric.get("name", ""))
                    metric_name = metric.get("name", "")
                    metric_value = metric.get("value")
                    
                    if metric_key == "Equity Final [$]" or metric_name == "Equity Final [$]" or metric_name == "最终权益":
                        equity_final = metric_value
                        print(f"  最终权益: {equity_final}")
                    elif metric_key == "Return [%]" or metric_name == "Return [%]" or metric_name == "总收益率":
                        total_return = metric_value
                        print(f"  总收益率: {total_return}%")
                
                # 检查初始资金
                initial_cash = currency_result.get("backtest_config", {}).get("initial_cash", 10000)
                print(f"  初始资金: {initial_cash}")
                
                # 计算收益率
                if equity_final and initial_cash:
                    calculated_return = ((equity_final - initial_cash) / initial_cash) * 100
                    print(f"  计算收益率: {calculated_return:.2f}%")
    
    # 检查summary部分
    if "summary" in backtest_result:
        print(f"\nSummary部分:")
        print(f"  total_return: {backtest_result['summary'].get('total_return')}")
        print(f"  total_initial_cash: {backtest_result['summary'].get('total_initial_cash')}")
        print(f"  total_equity: {backtest_result['summary'].get('total_equity')}")

# 运行测试
if __name__ == "__main__":
    test_merge_logic()
