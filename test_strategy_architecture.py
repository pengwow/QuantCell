#!/usr/bin/env python3
# 测试新的策略架构，比较 vectorbt 和 backtesting.py 的回测结果

import pandas as pd
import numpy as np
import sys
import os

# 添加项目根目录和 backend 目录到 Python 路径
project_root = os.path.dirname(os.path.abspath(__file__))
backend_path = os.path.join(project_root, 'backend')
sys.path.insert(0, project_root)
sys.path.insert(0, backend_path)

# 从策略模块导入所需类
from strategy.core import StrategyRunner
from strategy.sma_cross_core import SmaCrossCore


def load_test_data():
    """
    生成测试数据
    
    Returns:
        pd.DataFrame: 测试数据
    """
    # 生成模拟的 BTCUSDT 数据
    dates = pd.date_range('2023-01-01', periods=100, freq='1h')
    np.random.seed(42)
    
    # 生成随机价格数据
    close = 20000 + np.cumsum(np.random.randn(len(dates)) * 100)
    high = close + np.random.rand(len(dates)) * 50
    low = close - np.random.rand(len(dates)) * 50
    open_ = np.roll(close, 1)
    open_[0] = close[0] - np.random.rand() * 50
    volume = np.random.rand(len(dates)) * 1000
    
    df = pd.DataFrame({
        'Open': open_,
        'High': high,
        'Low': low,
        'Close': close,
        'Volume': volume
    }, index=dates)
    
    print(f"测试数据生成完成，共 {len(df)} 条记录")
    print(f"数据时间范围: {df.index.min()} 到 {df.index.max()}")
    
    return df


def test_strategy_architecture():
    """
    测试新的策略架构
    """
    print("=" * 60)
    print("测试新的策略架构")
    print("=" * 60)
    
    # 加载测试数据
    data = load_test_data()
    
    # 策略参数
    params = {
        'n1': 10,  # 短期移动平均线周期
        'n2': 20   # 长期移动平均线周期
    }
    
    # 创建策略核心
    strategy_core = SmaCrossCore(params)
    
    # 1. 使用 backtesting.py 回测
    print("\n" + "-" * 60)
    print("1. 使用 backtesting.py 回测")
    print("-" * 60)
    
    # 创建策略运行器，使用 backtesting.py 引擎
    runner = StrategyRunner(strategy_core, engine="backtesting.py")
    
    # 运行回测
    try:
        results_bt = runner.run(
            data, 
            cash=10000, 
            commission=0.001, 
            exclusive_orders=True
        )
        print("回测完成！")
        print("\n回测结果摘要:")
        print(results_bt)
    except Exception as e:
        print(f"backtesting.py 回测失败: {e}")
    
    # 2. 使用 vectorbt 回测
    print("\n" + "-" * 60)
    print("2. 使用 vectorbt 回测")
    print("-" * 60)
    
    # 切换到 vectorbt 引擎
    runner.switch_engine("vectorbt")
    
    # 运行回测
    try:
        results_vbt = runner.run(
            data, 
            init_cash=10000, 
            fees=0.001,
            freq="1h"  # 设置数据频率
        )
        print("回测完成！")
        print("\n回测结果摘要:")
        print(results_vbt.stats())
    except Exception as e:
        print(f"vectorbt 回测失败: {e}")
    
    print("\n" + "=" * 60)
    print("策略架构测试完成！")
    print("=" * 60)


if __name__ == "__main__":
    test_strategy_architecture()
