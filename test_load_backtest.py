#!/usr/bin/env python3
# 测试回测结果文件加载和指标提取

import sys
import os
import json
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.append(str(project_root))

# 回测结果文件目录
backtest_result_dir = project_root / "backend" / "backtest" / "results"

# 测试任务ID（使用最新的回测任务）
test_task_id = "5068f2ad-11d8-4921-988a-0a0167ea56aa"

# 测试加载回测结果文件
def test_load_backtest_result(task_id):
    print(f"测试加载回测结果文件，任务ID: {task_id}")
    
    # 构建文件路径
    result_path = backtest_result_dir / f"{task_id}.json"
    print(f"文件路径: {result_path}")
    
    # 检查文件是否存在
    if not result_path.exists():
        print(f"错误: 回测结果文件不存在")
        return None
    
    # 加载文件
    try:
        with open(result_path, "r", encoding="utf-8") as f:
            backtest_result = json.load(f)
        print("文件加载成功!")
        return backtest_result
    except Exception as e:
        print(f"错误: 加载文件失败 - {e}")
        return None

# 测试提取指标
def test_extract_metrics(backtest_result, task_id):
    print(f"\n测试提取指标，任务ID: {task_id}")
    
    backtest_info = {
        "id": task_id,
        "strategy_name": backtest_result.get("strategy_name", "Unknown"),
        "created_at": "20260127_135500",
        "status": backtest_result.get("status", "Unknown")
    }
    
    # 从合并结果中提取指标
    if "summary" in backtest_result:
        print("回测结果包含summary字段")
        # 多货币对回测结果
        if "total_return" in backtest_result["summary"]:
            print(f"summary中包含total_return: {backtest_result['summary']['total_return']}")
            backtest_info["total_return"] = round(float(backtest_result["summary"]["total_return"]), 2)
        if "average_max_drawdown" in backtest_result["summary"]:
            print(f"summary中包含average_max_drawdown: {backtest_result['summary']['average_max_drawdown']}")
            backtest_info["max_drawdown"] = round(float(backtest_result["summary"]["average_max_drawdown"]), 2)
    elif "metrics" in backtest_result:
        print("回测结果包含metrics字段")
        # 单个货币对回测结果
        for metric in backtest_result["metrics"]:
            # 同时检查指标的key和name字段
            metric_key = metric.get("key", metric.get("name", ""))
            metric_name = metric.get("name", "")
            
            if metric_key == "Return [%]" or metric_name == "Return [%]" or metric_name == "总收益率":
                print(f"找到Return [%]指标: {metric['value']}")
                backtest_info["total_return"] = round(float(metric["value"]), 2)
            elif metric_key == "Max. Drawdown [%]" or metric_name == "Max. Drawdown [%]" or metric_name == "最大回撤":
                print(f"找到Max. Drawdown [%]指标: {metric['value']}")
                backtest_info["max_drawdown"] = round(float(metric["value"]), 2)
    
    print("\n提取的指标:")
    print(f"  总收益率: {backtest_info.get('total_return', 'N/A')}")
    print(f"  最大回撤: {backtest_info.get('max_drawdown', 'N/A')}")
    
    return backtest_info

# 运行测试
print("开始测试回测结果文件加载和指标提取...\n")

# 加载回测结果
backtest_result = test_load_backtest_result(test_task_id)

if backtest_result:
    # 提取指标
    backtest_info = test_extract_metrics(backtest_result, test_task_id)
    print("\n测试完成!")
else:
    print("\n测试失败: 无法加载回测结果文件")
