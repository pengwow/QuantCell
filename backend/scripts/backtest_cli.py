#!/usr/bin/env python3
"""
QUANTCELL 回测命令行工具
支持通过命令行方式调用回测引擎进行回测
"""

from logging import root
import sys
import os
import argparse
import json
from pathlib import Path
import importlib.util
from typing import Dict, Any, Optional
from datetime import datetime
import pandas as pd
import numpy as np
from loguru import logger

# # 添加当前目录到路径
# root_path = Path(__file__).resolve().parent.parent.parent
# if str(root_path) not in sys.path:
#     sys.path.insert(0, str(root_path))


# # 添加策略目录到路径
# strategies_dir = os.path.join(os.path.dirname(root_path), 'strategies')
# if strategies_dir not in sys.path:
#     sys.path.insert(0, strategies_dir)

from strategy.core import VectorEngine, UnifiedStrategyBase
from strategy.adapters import VectorBacktestAdapter


def load_strategy(strategy_path: str, strategy_params: Dict[str, Any]):
    """
    动态加载策略
    
    参数：
    - strategy_path: 策略文件路径（不带.py后缀）
    - strategy_params: 策略参数
    
    返回：
    - 策略实例
    """
    try:
        # 导入策略模块
        module = importlib.import_module(strategy_path)
        
        # 获取策略类名（假设与文件名相同）
        # 查找所有类，找到继承自 UnifiedStrategyBase 的类
        strategy_class = None
        for name in dir(module):
            obj = getattr(module, name)
            if isinstance(obj, type) and issubclass(obj, UnifiedStrategyBase):
                strategy_class = obj
                break
        
        if strategy_class is None:
            raise AttributeError(f"在模块 {strategy_path} 中找不到策略类")
        
        # 创建策略实例
        strategy = strategy_class(strategy_params)
        
        print(f"成功加载策略: {strategy_class.__name__}")
        return strategy
        
    except Exception as e:
        print(f"加载策略失败: {strategy_path}")
        print(f"错误信息: {str(e)}")
        sys.exit(1)


def generate_test_data(n_steps: int = 1000, 
                    base_price: float = 50000.0,
                    volatility: float = 0.001) -> pd.DataFrame:
    """
    生成测试数据
    
    参数：
    - n_steps: 数据步数
    - base_price: 基础价格
    - volatility: 波动率
    
    返回：
    - DataFrame: OHLC数据
    """
    np.random.seed(42)
    
    # 生成价格数据
    price_changes = np.random.normal(0, volatility, n_steps)
    prices = base_price * (1 + np.cumsum(price_changes))
    
    # 生成日期
    dates = pd.date_range('2024-01-01', periods=n_steps, freq='H')
    
    # 创建 OHLC 数据
    df = pd.DataFrame({
        'Open': prices,
        'High': prices * 1.002,
        'Low': prices * 0.998,
        'Close': prices,
        'Volume': np.random.uniform(100, 1000, n_steps)
    }, index=dates)
    
    return df


def run_backtest(strategy_path: str,
              strategy_params: Dict[str, Any],
              data_path: Optional[str] = None,
              init_cash: float = 100000.0,
              fees: float = 0.001,
              slippage: float = 0.0001,
              output_format: str = 'json',
              output_file: Optional[str] = None) -> Dict[str, Any]:
    """
    运行回测
    
    参数：
    - strategy_path: 策略文件路径
    - strategy_params: 策略参数
    - data_path: 数据文件路径（可选）
    - init_cash: 初始资金
    - fees: 手续费率
    - slippage: 滑点
    - output_format: 输出格式（json/csv）
    - output_file: 输出文件路径（可选）
    
    返回：
    - dict: 回测结果
    """
    print("=" * 70)
    print("开始回测")
    print("=" * 70)
    print()
    
    # 加载策略
    strategy = load_strategy(strategy_path, strategy_params)
    
    # 准备数据
    if data_path:
        print(f"从文件加载数据: {data_path}")
        try:
            df = pd.read_csv(data_path, index_col=0, parse_dates=True)
            
            # 确保数据包含必要的列
            required_columns = ['Open', 'High', 'Low', 'Close', 'Volume']
            for col in required_columns:
                if col not in df.columns:
                    print(f"数据文件缺少必要列: {col}")
                    sys.exit(1)
                    
        except Exception as e:
            print(f"加载数据文件失败: {data_path}")
            print(f"错误信息: {str(e)}")
            sys.exit(1)
    else:
        print("生成测试数据")
        df = generate_test_data(n_steps=1000, base_price=50000.0, volatility=0.001)
    
    print(f"数据范围: {len(df)} 条K线")
    print(f"价格范围: [{df['Close'].min():.2f}, {df['Close'].max():.2f}]")
    print()
    
    # 创建适配器
    adapter = VectorBacktestAdapter(strategy)
    
    # 运行回测
    print("运行回测...")
    data_dict = {'BTCUSDT': df}
    results = adapter.run_backtest(
        data=data_dict,
        init_cash=init_cash,
        fees=fees,
        slippage=slippage
    )
    
    print("回测完成")
    print()
    
    # 输出结果
    output_results(results, output_format, output_file)
    
    return results


def output_results(results: Dict[str, Any], 
                output_format: str, 
                output_file: Optional[str]):
    """
    输出回测结果
    
    参数：
    - results: 回测结果
    - output_format: 输出格式（json/csv）
    - output_file: 输出文件路径（可选）
    """
    print("=" * 70)
    print("回测结果")
    print("=" * 70)
    print()
    
    for symbol, result in results.items():
        print(f"交易对: {symbol}")
        print(f"  最终现金: {result['cash'][0]:.2f}")
        print(f"  最终持仓: {result['positions'][-1, 0]:.4f}")
        print(f"  交易数量: {len(result['trades'])}")
        print()
        
        print("  绩效指标:")
        for key, value in result['metrics'].items():
            if isinstance(value, float):
                print(f"    {key}: {value:.4f}")
            else:
                print(f"    {key}: {value}")
        
        print()
    
    # 保存到文件
    if output_file:
        save_results(results, output_file, output_format)
    else:
        # 默认输出到当前目录
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        default_file = f"backtest_results_{timestamp}.{output_format}"
        save_results(results, default_file, output_format)
        print(f"结果已保存到: {default_file}")


def save_results(results: Dict[str, Any], 
              output_file: str, 
              output_format: str):
    """
    保存回测结果到文件
    
    参数：
    - results: 回测结果
    - output_file: 输出文件路径
    - output_format: 输出格式（json/csv）
    """
    try:
        if output_format == 'json':
            # 转换为可序列化的格式
            serializable_results = {}
            for symbol, result in results.items():
                serializable_results[symbol] = {
                    'symbol': symbol,
                    'cash': float(result['cash'][0]),
                    'final_position': float(result['positions'][-1, 0]),
                    'trade_count': len(result['trades']),
                    'metrics': {
                        k: float(v) if isinstance(v, (np.floating, float)) else int(v) if isinstance(v, (np.integer, int)) else str(v)
                        for k, v in result['metrics'].items()
                    }
                }
            
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(serializable_results, f, indent=2, ensure_ascii=False)
        
        elif output_format == 'csv':
            # 保存为 CSV 格式
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write("Symbol,Cash,FinalPosition,TradeCount,")
                f.write("TotalPnl,TotalFees,WinRate,SharpeRatio,FinalEquity\n")
                
                for symbol, result in results.items():
                    metrics = result['metrics']
                    f.write(f"{symbol},")
                    f.write(f"{result['cash'][0]:.2f},")
                    f.write(f"{result['positions'][-1, 0]:.4f},")
                    f.write(f"{len(result['trades'])},")
                    f.write(f"{metrics['total_pnl']:.2f},")
                    f.write(f"{metrics['total_fees']:.2f},")
                    f.write(f"{metrics['win_rate']:.4f},")
                    f.write(f"{metrics['sharpe_ratio']:.4f},")
                    f.write(f"{metrics['final_equity']:.2f}\n")
        
        print(f"结果已保存到: {output_file}")
        
    except Exception as e:
        print(f"保存结果失败: {output_file}")
        print(f"错误信息: {str(e)}")
        sys.exit(1)


def main():
    """
    主函数
    """
    parser = argparse.ArgumentParser(
        description='QUANTCELL 回测命令行工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 使用默认参数运行网格交易策略
  python backtest_cli.py --strategy grid_trading_v2
  
  # 指定策略参数
  python backtest_cli.py --strategy grid_trading_v2 --params '{"grid_count": 20, "position_size": 0.01}'
  
  # 使用自定义数据文件
  python backtest_cli.py --strategy grid_trading_v2 --data /path/to/data.csv
  
  # 指定输出格式和文件
  python backtest_cli.py --strategy grid_trading_v2 --output-format json --output results.json
        """
    )
    
    # 必需参数
    parser.add_argument(
        '--strategy', '-s',
        type=str,
        required=True,
        help='策略文件名（不带.py后缀），例如：grid_trading_v2'
    )
    
    # 可选参数
    parser.add_argument(
        '--params', '-p',
        type=str,
        default='{}',
        help='策略参数（JSON格式），例如：\'{"grid_count": 20, "position_size": 0.01}\''
    )
    
    parser.add_argument(
        '--data', '-d',
        type=str,
        default=None,
        help='数据文件路径（CSV格式），如果不指定则生成测试数据'
    )
    
    parser.add_argument(
        '--init-cash',
        type=float,
        default=100000.0,
        help='初始资金（默认：100000.0）'
    )
    
    parser.add_argument(
        '--fees',
        type=float,
        default=0.001,
        help='手续费率（默认：0.001）'
    )
    
    parser.add_argument(
        '--slippage',
        type=float,
        default=0.0001,
        help='滑点（默认：0.0001）'
    )
    
    parser.add_argument(
        '--output-format', '-f',
        type=str,
        choices=['json', 'csv'],
        default='json',
        help='输出格式：json 或 csv（默认：json）'
    )
    
    parser.add_argument(
        '--output', '-o',
        type=str,
        default=None,
        help='输出文件路径，如果不指定则自动生成文件名'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='显示详细日志'
    )
    
    args = parser.parse_args()
    
    # 解析策略参数
    try:
        strategy_params = json.loads(args.params)
    except json.JSONDecodeError as e:
        print(f"策略参数解析失败: {args.params}")
        print(f"错误信息: {str(e)}")
        sys.exit(1)
    
    # 运行回测
    try:
        results = run_backtest(
            strategy_path=args.strategy,
            strategy_params=strategy_params,
            data_path=args.data,
            init_cash=args.init_cash,
            fees=args.fees,
            slippage=args.slippage,
            output_format=args.output_format,
            output_file=args.output
        )
        
        print("=" * 70)
        print("回测成功完成！")
        print("=" * 70)
        
    except KeyboardInterrupt:
        print("\n回测被用户中断")
        sys.exit(0)
    except Exception as e:
        print(f"回测失败: {str(e)}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
