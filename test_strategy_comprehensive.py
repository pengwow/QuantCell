#!/usr/bin/env python3
# 综合测试脚本，测试不同数据类型、策略参数和回测引擎参数

import pandas as pd
import numpy as np
import sys
import os
from datetime import datetime, timedelta

# 添加项目根目录和 backend 目录到 Python 路径
project_root = os.path.dirname(os.path.abspath(__file__))
backend_path = os.path.join(project_root, 'backend')
sys.path.insert(0, project_root)
sys.path.insert(0, backend_path)

# 导入策略相关类
from backtest.strategies.core import StrategyRunner
from backtest.strategies.common_strategies import (
    RSIStrategy,
    MACDStrategy,
    BollingerBandsStrategy,
    MultiFactorStrategy
)
from backtest.strategies.result_analysis import ResultAnalyzer


def generate_test_data(duration_days=30, freq='1h', asset='BTCUSDT', market_type='trend'):
    """
    生成测试数据
    
    Args:
        duration_days: 数据持续天数
        freq: 数据频率
        asset: 资产名称
        market_type: 市场类型 ('trend' 或 'range')
    
    Returns:
        pd.DataFrame: 测试数据
    """
    # 生成日期范围
    end_date = pd.Timestamp.now()
    start_date = end_date - pd.Timedelta(days=duration_days)
    dates = pd.date_range(start=start_date, end=end_date, freq=freq)
    
    # 设置随机种子，确保结果可复现
    np.random.seed(42)
    
    # 生成价格数据
    base_price = 20000 if asset == 'BTCUSDT' else 100
    
    if market_type == 'trend':
        # 趋势市场
        trend = np.linspace(0, 1, len(dates)) * 10000  # 上升趋势
        noise = np.cumsum(np.random.randn(len(dates)) * 50)
        close = base_price + trend + noise
    else:
        # 震荡市场
        volatility = np.sin(np.linspace(0, 4 * np.pi, len(dates))) * 5000
        noise = np.random.randn(len(dates)) * 50
        close = base_price + volatility + noise
    
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


def test_different_data_frequencies():
    """
    测试不同数据频率
    """
    print("\n" + "="*60)
    print("测试不同数据频率")
    print("="*60)
    
    frequencies = ['1min', '1h', '1d']
    
    for freq in frequencies:
        print(f"\n测试频率: {freq}")
        print("-"*40)
        
        # 生成测试数据
        data = generate_test_data(duration_days=10, freq=freq, market_type='trend')
        
        # 创建策略
        strategy_core = RSIStrategy({
            'rsi_period': 14,
            'oversold': 30,
            'overbought': 70
        })
        
        # 创建策略运行器
        runner = StrategyRunner(strategy_core, engine="backtesting.py")
        
        try:
            # 运行回测
            bt_result = runner.run(
                data, 
                cash=10000, 
                commission=0.001,
                exclusive_orders=True
            )
            print(f"backtesting.py 回测成功，交易次数: {bt_result.get('# Trades', 0)}")
            
            # 切换到 vectorbt
            runner.switch_engine("vectorbt")
            vbt_result = runner.run(
                data, 
                init_cash=10000, 
                fees=0.001,
                freq=data.index.freq
            )
            print(f"vectorbt 回测成功，交易次数: {vbt_result.stats().get('Total Trades', 0)}")
        except Exception as e:
            print(f"回测失败: {e}")


def test_different_strategy_params():
    """
    测试不同策略参数组合
    """
    print("\n" + "="*60)
    print("测试不同策略参数组合")
    print("="*60)
    
    # 生成测试数据
    data = generate_test_data(duration_days=30, freq='1h', market_type='trend')
    
    # 测试 RSI 策略的不同参数组合
    rsi_params = [
        {'rsi_period': 7, 'oversold': 25, 'overbought': 75},
        {'rsi_period': 14, 'oversold': 30, 'overbought': 70},
        {'rsi_period': 21, 'oversold': 35, 'overbought': 65}
    ]
    
    for params in rsi_params:
        print(f"\n测试 RSI 参数: {params}")
        print("-"*40)
        
        strategy_core = RSIStrategy(params)
        runner = StrategyRunner(strategy_core, engine="backtesting.py")
        
        try:
            bt_result = runner.run(
                data, 
                cash=10000, 
                commission=0.001,
                exclusive_orders=True
            )
            print(f"backtesting.py 回测成功，总收益率: {bt_result.get('Return [%]', 0):.2f}%")
            
            runner.switch_engine("vectorbt")
            vbt_result = runner.run(
                data, 
                init_cash=10000, 
                fees=0.001,
                freq=data.index.freq
            )
            print(f"vectorbt 回测成功，总收益率: {vbt_result.stats().get('Total Return [%]', 0):.2f}%")
        except Exception as e:
            print(f"回测失败: {e}")


def test_different_engine_params():
    """
    测试不同回测引擎参数
    """
    print("\n" + "="*60)
    print("测试不同回测引擎参数")
    print("="*60)
    
    # 生成测试数据
    data = generate_test_data(duration_days=30, freq='1h', market_type='trend')
    
    # 创建策略
    strategy_core = MACDStrategy({
        'fast_period': 12,
        'slow_period': 26,
        'signal_period': 9
    })
    
    # 测试不同手续费
    commission_rates = [0.0001, 0.001, 0.005]
    
    for commission in commission_rates:
        print(f"\n测试手续费: {commission:.4f}")
        print("-"*40)
        
        runner = StrategyRunner(strategy_core, engine="backtesting.py")
        
        try:
            bt_result = runner.run(
                data, 
                cash=10000, 
                commission=commission,
                exclusive_orders=True
            )
            print(f"backtesting.py 回测成功，总收益率: {bt_result.get('Return [%]', 0):.2f}%")
            
            runner.switch_engine("vectorbt")
            vbt_result = runner.run(
                data, 
                init_cash=10000, 
                fees=commission,
                freq=data.index.freq
            )
            print(f"vectorbt 回测成功，总收益率: {vbt_result.stats().get('Total Return [%]', 0):.2f}%")
        except Exception as e:
            print(f"回测失败: {e}")


def test_multi_asset():
    """
    测试多资产策略
    """
    print("\n" + "="*60)
    print("测试多资产策略")
    print("="*60)
    
    # 生成多资产测试数据
    assets = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT']
    data_dict = {}
    
    for asset in assets:
        data_dict[asset] = generate_test_data(duration_days=30, freq='1h', asset=asset, market_type='trend')
    
    # 测试多因子策略
    strategy_core = MultiFactorStrategy({
        'rsi_period': 14,
        'fast_period': 12,
        'slow_period': 26,
        'signal_period': 9,
        'short_sma_period': 10,
        'long_sma_period': 20,
        'rsi_oversold': 40
    })
    
    for asset in assets:
        print(f"\n测试资产: {asset}")
        print("-"*40)
        
        runner = StrategyRunner(strategy_core, engine="backtesting.py")
        
        try:
            bt_result = runner.run(
                data_dict[asset], 
                cash=10000, 
                commission=0.001,
                exclusive_orders=True
            )
            print(f"backtesting.py 回测成功，总收益率: {bt_result.get('Return [%]', 0):.2f}%")
            
            runner.switch_engine("vectorbt")
            vbt_result = runner.run(
                data_dict[asset], 
                init_cash=10000, 
                fees=0.001,
                freq=data_dict[asset].index.freq
            )
            print(f"vectorbt 回测成功，总收益率: {vbt_result.stats().get('Total Return [%]', 0):.2f}%")
        except Exception as e:
            print(f"回测失败: {e}")


def test_different_market_environments():
    """
    测试不同市场环境
    """
    print("\n" + "="*60)
    print("测试不同市场环境")
    print("="*60)
    
    market_types = ['trend', 'range']
    
    for market_type in market_types:
        print(f"\n测试市场类型: {market_type}")
        print("-"*40)
        
        # 生成测试数据
        data = generate_test_data(duration_days=30, freq='1h', market_type=market_type)
        
        # 测试不同策略
        strategies = [
            ('RSI 策略', RSIStrategy({'rsi_period': 14, 'oversold': 30, 'overbought': 70})),
            ('MACD 策略', MACDStrategy({'fast_period': 12, 'slow_period': 26, 'signal_period': 9})),
            ('Bollinger Bands 策略', BollingerBandsStrategy({'bb_period': 20, 'bb_std': 2}))
        ]
        
        for strategy_name, strategy_core in strategies:
            print(f"\n  测试策略: {strategy_name}")
            
            runner = StrategyRunner(strategy_core, engine="backtesting.py")
            
            try:
                bt_result = runner.run(
                    data, 
                    cash=10000, 
                    commission=0.001,
                    exclusive_orders=True
                )
                bt_return = bt_result.get('Return [%]', 0)
                
                runner.switch_engine("vectorbt")
                vbt_result = runner.run(
                    data, 
                    init_cash=10000, 
                    fees=0.001,
                    freq=data.index.freq
                )
                vbt_return = vbt_result.stats().get('Total Return [%]', 0)
                
                print(f"    backtesting.py: {bt_return:.2f}%")
                print(f"    vectorbt: {vbt_return:.2f}%")
            except Exception as e:
                print(f"    回测失败: {e}")


def main():
    """
    主测试函数
    """
    print("="*80)
    print("综合策略测试")
    print("="*80)
    
    # 运行所有测试
    test_different_data_frequencies()
    test_different_strategy_params()
    test_different_engine_params()
    test_multi_asset()
    test_different_market_environments()
    
    print("\n" + "="*80)
    print("所有测试完成!")
    print("="*80)


if __name__ == "__main__":
    main()
