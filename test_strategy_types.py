#!/usr/bin/env python3
# 测试不同策略类型在两种回测引擎上的表现

import pandas as pd
import numpy as np
import sys
import os

# 添加项目根目录和 backend 目录到 Python 路径
project_root = os.path.dirname(os.path.abspath(__file__))
backend_path = os.path.join(project_root, 'backend')
sys.path.insert(0, project_root)
sys.path.insert(0, backend_path)

# 导入策略相关类
from strategy.core import StrategyRunner
from strategy.common_strategies import (
    RSIStrategy,
    MACDStrategy,
    BollingerBandsStrategy,
    MultiFactorStrategy
)
from strategy.result_analysis import ResultAnalyzer


def generate_test_data(duration_days=30, freq='1h', asset='BTCUSDT'):
    """
    生成测试数据
    
    Args:
        duration_days: 数据持续天数
        freq: 数据频率
        asset: 资产名称
    
    Returns:
        pd.DataFrame: 测试数据
    """
    # 生成日期范围
    end_date = pd.Timestamp.now()
    start_date = end_date - pd.Timedelta(days=duration_days)
    dates = pd.date_range(start=start_date, end=end_date, freq=freq)
    
    # 设置随机种子，确保结果可复现
    np.random.seed(42)
    
    # 生成随机价格数据
    base_price = 20000 if asset == 'BTCUSDT' else 100
    close = base_price + np.cumsum(np.random.randn(len(dates)) * 50)
    
    # 生成 OHLC 数据
    high = close + np.random.rand(len(dates)) * 100
    low = close - np.random.rand(len(dates)) * 100
    open_ = np.roll(close, 1)
    open_[0] = close[0] - np.random.rand() * 50
    volume = np.random.rand(len(dates)) * 1000
    
    # 创建 DataFrame
    df = pd.DataFrame({
        'Open': open_,
        'High': high,
        'Low': low,
        'Close': close,
        'Volume': volume
    }, index=dates)
    
    # 保存收盘价到指标中（用于 BollingerBandsStrategy）
    df['close'] = df['Close']
    
    return df


def test_strategy(strategy_class, params, data, strategy_name):
    """
    测试单个策略在两种回测引擎上的表现
    
    Args:
        strategy_class: 策略类
        params: 策略参数
        data: 测试数据
        strategy_name: 策略名称
    
    Returns:
        tuple: (backtesting.py 结果, vectorbt 结果)
    """
    print(f"\n{'='*60}")
    print(f"测试策略: {strategy_name}")
    print(f"{'='*60}")
    
    # 创建策略核心
    strategy_core = strategy_class(params)
    
    # 创建策略运行器
    runner = StrategyRunner(strategy_core, engine="backtesting.py")
    
    # 运行 backtesting.py 回测
    print(f"\n1. 使用 backtesting.py 回测")
    print(f"-"*40)
    try:
        bt_result = runner.run(
            data, 
            cash=10000, 
            commission=0.001, 
            exclusive_orders=True
        )
        print("backtesting.py 回测完成!")
    except Exception as e:
        print(f"backtesting.py 回测失败: {e}")
        bt_result = None
    
    # 切换到 vectorbt
    runner.switch_engine("vectorbt")
    
    # 运行 vectorbt 回测
    print(f"\n2. 使用 vectorbt 回测")
    print(f"-"*40)
    try:
        vbt_result = runner.run(
            data, 
            init_cash=10000, 
            fees=0.001,
            freq=data.index.freq
        )
        print("vectorbt 回测完成!")
    except Exception as e:
        print(f"vectorbt 回测失败: {e}")
        vbt_result = None
    
    return bt_result, vbt_result


def main():
    """
    主测试函数
    """
    print("="*60)
    print("测试不同策略类型在两种回测引擎上的表现")
    print("="*60)
    
    # 生成测试数据
    print("\n生成测试数据...")
    data = generate_test_data(duration_days=30, freq='1h', asset='BTCUSDT')
    print(f"测试数据生成完成，共 {len(data)} 条记录")
    print(f"数据时间范围: {data.index.min()} 到 {data.index.max()}")
    
    # 定义要测试的策略和参数
    strategies_to_test = [
        {
            'class': RSIStrategy,
            'params': {
                'rsi_period': 14,
                'oversold': 30,
                'overbought': 70,
                'stop_loss_pct': 0.02,
                'take_profit_pct': 0.05
            },
            'name': 'RSI 策略'
        },
        {
            'class': MACDStrategy,
            'params': {
                'fast_period': 12,
                'slow_period': 26,
                'signal_period': 9
            },
            'name': 'MACD 策略'
        },
        {
            'class': BollingerBandsStrategy,
            'params': {
                'bb_period': 20,
                'bb_std': 2
            },
            'name': 'Bollinger Bands 策略'
        },
        {
            'class': MultiFactorStrategy,
            'params': {
                'rsi_period': 14,
                'fast_period': 12,
                'slow_period': 26,
                'signal_period': 9,
                'short_sma_period': 10,
                'long_sma_period': 20,
                'rsi_oversold': 40
            },
            'name': '多因子策略'
        }
    ]
    
    # 测试所有策略
    all_results = []
    for strategy_info in strategies_to_test:
        bt_result, vbt_result = test_strategy(
            strategy_info['class'],
            strategy_info['params'],
            data,
            strategy_info['name']
        )
        
        if bt_result is not None and vbt_result is not None:
            all_results.append({
                'name': strategy_info['name'],
                'bt_result': bt_result,
                'vbt_result': vbt_result
            })
    
    # 分析结果
    if all_results:
        print(f"\n{'='*60}")
        print("分析回测结果")
        print(f"{'='*60}")
        
        # 对每个策略生成比较报告
        for result in all_results:
            print(f"\n\n{'='*80}")
            print(f"策略: {result['name']} 回测结果比较")
            print(f"{'='*80}")
            
            # 创建结果分析器
            analyzer = ResultAnalyzer()
            analyzer.add_result(result['bt_result'], 'backtesting.py')
            analyzer.add_result(result['vbt_result'], 'vectorbt')
            
            # 生成比较报告
            report = analyzer.generate_comparison_report()
            print(report)
    
    print(f"\n{'='*60}")
    print("所有策略测试完成!")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
