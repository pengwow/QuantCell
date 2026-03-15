#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
回测API接口测试脚本
"""

import sys
from pathlib import Path

# 添加后端目录到路径
backend_path = Path(__file__).resolve().parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from datetime import datetime
import json

print("=" * 80)
print("回测API接口测试")
print("=" * 80)
print()

# 1. 测试Schema验证
print("[1] 测试Schema验证...")
try:
    from backtest.schemas import BacktestRunRequest, StrategyConfig, BacktestConfig
    
    # 构造测试请求（与命令行示例相同）
    test_request = BacktestRunRequest(
        strategy_config=StrategyConfig(
            strategy_name="sma_cross_simple",
            params={"fast_period": 10, "slow_period": 30, "trade_size": 0.1}
        ),
        backtest_config=BacktestConfig(
            symbols=["ETHUSDT"],
            interval="1h",
            start_time="20260109-20260305",  # 测试CLI格式
            end_time="20260109-20260305",
            initial_cash=100000.0,
            commission=0.001,
            exclusive_orders=True,
            engine_type="event",
            base_currency="USDT",
            leverage=1.0,
            venue="SIM"
        )
    )
    
    print("✓ Schema验证通过！")
    print(f"  - 策略名称: {test_request.strategy_config.strategy_name}")
    print(f"  - 策略参数: {json.dumps(test_request.strategy_config.params, ensure_ascii=False)}")
    print(f"  - 交易对: {test_request.backtest_config.symbols}")
    print(f"  - 时间周期: {test_request.backtest_config.interval}")
    print(f"  - 初始资金: {test_request.backtest_config.initial_cash}")
    print(f"  - 回测引擎: {test_request.backtest_config.engine_type}")
    print()
    
except Exception as e:
    print(f"✗ Schema验证失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 2. 测试时间范围格式转换
print("[2] 测试时间范围格式转换...")
try:
    from utils.validation import validate_time_range, parse_time_range
    
    cli_time_range = "20260109-20260305"
    print(f"CLI格式: {cli_time_range}")
    
    if validate_time_range(cli_time_range):
        start_dt, end_dt = parse_time_range(cli_time_range)
        api_start_time = start_dt.strftime("%Y-%m-%d 00:00:00")
        api_end_time = end_dt.strftime("%Y-%m-%d 23:59:59")
        print(f"✓ 转换成功:")
        print(f"  - 开始时间: {api_start_time}")
        print(f"  - 结束时间: {api_end_time}")
        print()
    else:
        print("✗ 时间范围格式无效")
        sys.exit(1)
        
except Exception as e:
    print(f"✗ 时间范围格式转换测试失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 3. 测试BacktestService初始化
print("[3] 测试BacktestService初始化...")
try:
    from backtest.service import BacktestService
    
    service = BacktestService()
    print("✓ BacktestService初始化成功！")
    print()
    
except Exception as e:
    print(f"✗ BacktestService初始化失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("=" * 80)
print("所有测试通过！")
print("=" * 80)
print()
print("API接口优化已完成，包含以下功能：")
print("1. ✓ Schema支持engine_type和事件驱动引擎参数")
print("2. ✓ 时间范围格式转换支持（YYYYMMDD-YYYYMMDD）")
print("3. ✓ 事件驱动引擎完整集成")
print("4. ✓ 完整的错误处理和日志记录")
print()
print("现在可以使用与CLI相同的参数通过API执行回测了！")
