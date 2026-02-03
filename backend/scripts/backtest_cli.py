#!/usr/bin/env python3
"""
QUANTCELL 回测命令行工具
支持通过命令行方式调用回测引擎进行回测
"""

from loguru import logger
import sys
import os
import json
from pathlib import Path
import importlib.util
from typing import Dict, Any, Optional, List
from datetime import datetime
import pandas as pd
import numpy as np
import typer
from typing_extensions import Annotated

# 添加后端目录到路径
backend_path = Path(__file__).resolve().parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))
logger.info(f"添加后端目录到路径: {backend_path}")
# 添加策略目录到路径
strategies_dir = os.path.join(backend_path, 'strategies')
logger.info(f"添加策略目录到路径: {strategies_dir}")
if strategies_dir not in sys.path:
    sys.path.insert(0, strategies_dir)

backtest_results_dir = os.path.join(backend_path, 'backtest', 'results')
logger.info(f"添加回测结果目录到路径: {backtest_results_dir}")

from strategy.core import VectorEngine, StrategyBase
from strategy.adapters import VectorBacktestAdapter

# 创建Typer应用
app = typer.Typer(
    name="backtest",
    help="QUANTCELL 回测命令行工具",
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

  # 指定时间范围
  python backtest_cli.py --strategy grid_trading_v2 --time-range 20240101-20241231

  # 指定多个货币对
  python backtest_cli.py --strategy grid_trading_v2 --symbols BTC/USDT,ETH/USDT

  # 指定多个时间周期
  python backtest_cli.py --strategy grid_trading_v2 --timeframes 15m,30m,1h

  # 指定交易模式
  python backtest_cli.py --strategy grid_trading_v2 --trading-mode futures

  # 组合使用所有参数
  python backtest_cli.py --strategy grid_trading_v2 \\
    --time-range 20240101-20241231 \\
    --symbols BTC/USDT,ETH/USDT \\
    --timeframes 15m,30m,1h \\
    --trading-mode futures \\
    --output results.json
    """
)


def get_system_config() -> Dict[str, Any]:
    """
    从系统配置表读取默认值

    返回：
    - dict: 包含默认交易模式和默认时间周期
    """
    try:
        from collector.db.connection import get_db_connection
        from collector.db.models import SystemConfig

        conn = get_db_connection()
        # 读取交易模式默认值
        trading_mode_config = conn.execute(
            "SELECT value FROM system_config WHERE key = 'default_trading_mode'"
        ).fetchone()
        default_trading_mode = trading_mode_config[0] if trading_mode_config else 'spot'

        # 读取时间周期默认值
        timeframes_config = conn.execute(
            "SELECT value FROM system_config WHERE key = 'default_timeframes'"
        ).fetchone()
        default_timeframes = timeframes_config[0].split(',') if timeframes_config else ['1h']

        return {
            'default_trading_mode': default_trading_mode,
            'default_timeframes': default_timeframes
        }
    except Exception as e:
        logger.warning(f"从系统配置读取默认值失败: {e}")
        return {
            'default_trading_mode': 'spot',
            'default_timeframes': ['1h']
        }


def validate_time_range(time_range: str) -> bool:
    """
    验证时间范围格式（YYYYMMDD-YYYYMMDD）

    参数：
    - time_range: 时间范围字符串

    返回：
    - bool: 格式正确返回True，否则返回False
    """
    if not time_range:
        return True  # 允许为空
    try:
        parts = time_range.split('-')
        if len(parts) != 2:
            return False

        start_date = datetime.strptime(parts[0], '%Y%m%d')
        end_date = datetime.strptime(parts[1], '%Y%m%d')

        if start_date >= end_date:
            return False

        return True
    except ValueError:
        return False


def validate_symbols(symbols: str) -> bool:
    """
    验证货币对格式

    参数：
    - symbols: 货币对字符串

    返回：
    - bool: 格式正确返回True，否则返回False
    """
    if not symbols:
        return True  # 允许为空，使用默认值

    symbol_list = symbols.split(',')
    for symbol in symbol_list:
        symbol = symbol.strip()
        if not symbol:  # 允许空字符串
            continue
    return True


def validate_timeframes(timeframes: str) -> bool:
    """
    验证时间周期

    参数：
    - timeframes: 时间周期字符串

    返回：
    - bool: 周期有效返回True，否则返回False
    """
    if not timeframes:
        return True  # 允许为空，使用默认值

    valid_timeframes = ['15m', '30m', '1h', '4h', '1d']
    timeframe_list = timeframes.split(',')

    for timeframe in timeframe_list:
        timeframe = timeframe.strip()
        if timeframe and timeframe not in valid_timeframes:
            return False

    return True


def validate_trading_mode(mode: Optional[str]) -> bool:
    """
    验证交易模式

    参数：
    - mode: 交易模式字符串

    返回：
    - bool: 模式有效返回True，否则返回False
    """
    if mode is None:
        return True  # 允许为空，使用默认值
    valid_modes = ['spot', 'futures', 'perpetual']
    return mode in valid_modes


def load_klines_from_db(symbols: List[str],
                       timeframes: List[str],
                       time_range: Optional[str],
                       trading_mode: Optional[str]) -> Dict[str, pd.DataFrame]:
    """
    从数据库加载K线数据

    参数：
    - symbols: 货币对列表
    - timeframes: 时间周期列表
    - time_range: 时间范围（YYYYMMDD-YYYYMMDD）
    - trading_mode: 交易模式（spot, futures, perpetual）

    返回：
    - dict: {symbol_timeframe: DataFrame}
    """
    from collector.db.connection import get_db_connection
    from collector.db.models import CryptoSpotKline, CryptoFutureKline

    conn = get_db_connection()
    # 注意：不关闭连接，因为 get_db_connection() 使用单例模式管理连接

    # 解析时间范围
    start_date, end_date = parse_time_range(time_range)

    # 选择数据表
    if trading_mode == 'spot':
        KlineModel = CryptoSpotKline
    elif trading_mode in ['futures', 'perpetual']:
        KlineModel = CryptoFutureKline
    else:
        raise ValueError(f"不支持的交易模式: {trading_mode}")

    # 查询数据
    results = {}
    for symbol in symbols:
        for timeframe in timeframes:
            key = f"{symbol}_{timeframe}"

            # 构建查询条件
            conditions = f"symbol = '{symbol}' AND interval = '{timeframe}'"
            if start_date:
                # 转换为毫秒级时间戳
                start_timestamp = int(start_date.timestamp() * 1000)
                conditions += f" AND timestamp >= {start_timestamp}"
            if end_date:
                # 转换为毫秒级时间戳
                end_timestamp = int(end_date.timestamp() * 1000)
                conditions += f" AND timestamp <= {end_timestamp}"

            # 生成完整 SQL
            query = f"""
                SELECT timestamp, open, high, low, close, volume
                FROM {KlineModel.__tablename__}
                WHERE {conditions}
                ORDER BY timestamp ASC
            """
            logger.info(f"执行查询: {query}")
            # 执行查询
            cursor = conn.cursor()
            cursor.execute(query)
            klines = cursor.fetchall()

            # 转换为 DataFrame
            if klines:
                df = pd.DataFrame(klines, columns=['timestamp', 'Open', 'High', 'Low', 'Close', 'Volume'])
                # 数据库中的timestamp是毫秒级，需要转换为秒级再转换为datetime
                df['timestamp'] = pd.to_datetime(df['timestamp'].astype(float) / 1000, unit='s')
                df.set_index('timestamp', inplace=True)
                results[key] = df
            else:
                logger.warning(f"未找到数据: {key}")

    return results


def parse_time_range(time_range: Optional[str]) -> tuple:
    """
    解析时间范围（YYYYMMDD-YYYYMMDD）

    参数：
    - time_range: 时间范围字符串

    返回：
    - tuple: (start_date, end_date)
    """
    if time_range is None:
        return None, None

    parts = time_range.split('-')
    if len(parts) != 2:
        raise ValueError(f"时间范围格式错误: {time_range}，应为 YYYYMMDD-YYYYMMDD")

    start_date = datetime.strptime(parts[0], '%Y%m%d')
    end_date = datetime.strptime(parts[1], '%Y%m%d')

    if start_date >= end_date:
        raise ValueError(f"开始日期必须早于结束日期: {start_date} >= {end_date}")

    return start_date, end_date


def load_strategy(strategy_name: str, strategy_params: Dict[str, Any]):
    """
    动态加载策略

    参数：
    - strategy_name: 策略文件名（不带.py后缀）
    - strategy_params: 策略参数

    返回：
    - 策略实例
    """
    try:
        # 清除模块缓存，确保加载最新代码
        if strategy_name in sys.modules:
            del sys.modules[strategy_name]

        # 检查策略文件是否存在
        strategy_file = os.path.join(strategies_dir, f"{strategy_name}.py")
        logger.info(f"尝试加载策略文件: {strategy_file}")
        if not os.path.exists(strategy_file):
            raise FileNotFoundError(f"策略文件 {strategy_name}.py 不存在")

        # 导入策略模块
        module = importlib.import_module(strategy_name)

        # 获取策略类名（查找所有继承自 StrategyBase 的类，但排除 StrategyBase 本身）
        strategy_class = None
        for name in dir(module):
            obj = getattr(module, name)
            if isinstance(obj, type) and issubclass(obj, StrategyBase) and obj != StrategyBase:
                strategy_class = obj
                logger.info(f"找到策略类: {name}")
                break

        if strategy_class is None:
            raise AttributeError(f"在模块 {strategy_name} 中找不到策略类")

        # 创建策略实例
        strategy = strategy_class(strategy_params)

        print(f"成功加载策略: {strategy_class.__name__}")
        return strategy

    except Exception as e:
        print(f"加载策略失败: {strategy_name}")
        print(f"错误信息: {str(e)}")
        raise typer.Exit(1)


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

        # 显示策略订单和指标
        if 'orders' in result and result['orders']:
            print(f"  策略订单数量: {len(result['orders'])}")
            for i, order in enumerate(result['orders'][:10], 1):
                print(f"    订单 {i}: {order.get('order_id', 'N/A')} - {order.get('direction', 'N/A')} @ {order.get('price', 0):.2f}")
            if len(result['orders']) > 10:
                print(f"    ... 还有 {len(result['orders']) - 10} 个订单")

        if 'indicators' in result and result['indicators']:
            print(f"  策略指标数量: {len(result['indicators'])}")
            for key, value in list(result['indicators'].items())[:10]:
                if isinstance(value, float):
                    print(f"    {key}: {value:.4f}")
                else:
                    print(f"    {key}: {value}")
            if len(result['indicators']) > 10:
                print(f"    ... 还有 {len(result['indicators']) - 10} 个指标")

        if 'strategy_trades' in result and result['strategy_trades']:
            print(f"  策略交易数量: {len(result['strategy_trades'])}")
            for i, trade in enumerate(result['strategy_trades'][:10], 1):
                print(f"    交易 {i}: {trade.get('direction', 'N/A')} @ {trade.get('price', 0):.2f}")
            if len(result['strategy_trades']) > 10:
                print(f"    ... 还有 {len(result['strategy_trades']) - 10} 个交易")

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
                # 序列化订单数据
                orders_serializable = []
                if 'orders' in result and result['orders']:
                    for order in result['orders']:
                        orders_serializable.append({
                            'order_id': order.get('order_id', ''),
                            'direction': order.get('direction', ''),
                            'price': float(order.get('price', 0)) if order.get('price') is not None else None,
                            'volume': float(order.get('volume', 0)) if order.get('volume') is not None else None,
                            'status': order.get('status', ''),
                            'timestamp': order.get('timestamp', '').isoformat() if order.get('timestamp') else ''
                        })

                # 序列化指标数据
                indicators_serializable = {}
                if 'indicators' in result and result['indicators']:
                    for key, value in result['indicators'].items():
                        if isinstance(value, (np.floating, float)):
                            indicators_serializable[key] = float(value)
                        elif isinstance(value, (np.integer, int)):
                            indicators_serializable[key] = int(value)
                        elif isinstance(value, datetime):
                            indicators_serializable[key] = value.isoformat()
                        else:
                            indicators_serializable[key] = str(value)

                # 序列化策略交易数据
                strategy_trades_serializable = []
                if 'strategy_trades' in result and result['strategy_trades']:
                    for trade in result['strategy_trades']:
                        strategy_trades_serializable.append({
                            'direction': trade.get('direction', ''),
                            'price': float(trade.get('price', 0)) if trade.get('price') is not None else None,
                            'volume': float(trade.get('volume', 0)) if trade.get('volume') is not None else None,
                            'timestamp': trade.get('timestamp', '').isoformat() if trade.get('timestamp') else ''
                        })

                serializable_results[symbol] = {
                    'symbol': symbol,
                    'cash': float(result['cash'][0]),
                    'final_position': float(result['positions'][-1, 0]),
                    'trade_count': len(result['trades']),
                    'metrics': {
                        k: float(v) if isinstance(v, (np.floating, float)) else int(v) if isinstance(v, (np.integer, int)) else str(v)
                        for k, v in result['metrics'].items()
                    },
                    'orders': orders_serializable,
                    'indicators': indicators_serializable,
                    'strategy_trades': strategy_trades_serializable
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
        raise typer.Exit(1)


@app.command()
def run(
    strategy: Annotated[str, typer.Option("--strategy", "-s", help="策略文件名（不带.py后缀），例如：grid_trading_v2")],
    params: Annotated[str, typer.Option("--params", "-p", help="策略参数（JSON格式），例如：'{\"grid_count\": 20, \"position_size\": 0.01}'")] = "{}",
    data: Annotated[Optional[str], typer.Option("--data", "-d", help="数据文件路径（CSV格式），如果不指定则从数据库加载")] = None,
    init_cash: Annotated[float, typer.Option("--init-cash", help="初始资金")] = 100000.0,
    fees: Annotated[float, typer.Option("--fees", help="手续费率")] = 0.001,
    slippage: Annotated[float, typer.Option("--slippage", help="滑点")] = 0.0001,
    output_format: Annotated[str, typer.Option("--output-format", "-f", help="输出格式：json 或 csv")] = "json",
    output: Annotated[Optional[str], typer.Option("--output", "-o", help="输出文件路径，如果不指定则自动生成文件名")] = None,
    time_range: Annotated[Optional[str], typer.Option("--time-range", help="回测时间范围（格式：YYYYMMDD-YYYYMMDD），例如：20240101-20241231")] = None,
    symbols: Annotated[Optional[str], typer.Option("--symbols", help="货币对列表（多个货币对使用英文逗号分隔），例如：BTC/USDT,ETH/USDT,BNB/USDT")] = None,
    timeframes: Annotated[Optional[str], typer.Option("--timeframes", help="时间周期列表（多个周期使用英文逗号分隔），支持：15m,30m,1h,4h,1d，例如：15m,30m,1h")] = None,
    trading_mode: Annotated[Optional[str], typer.Option("--trading-mode", help="交易模式（spot=现货，futures=合约，perpetual=永续合约），默认从系统配置读取")] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="显示详细日志")] = False
):
    """
    运行回测
    """
    print("=" * 70)
    print("开始回测")
    print("=" * 70)
    print()

    # 验证参数
    if time_range and not validate_time_range(time_range):
        print(f"错误：时间范围格式错误: {time_range}")
        print("正确格式：YYYYMMDD-YYYYMMDD，例如：20240101-20241231")
        raise typer.Exit(1)

    if symbols and not validate_symbols(symbols):
        print(f"错误：货币对格式错误: {symbols}")
        print("正确格式：BTC/USDT,ETH/USDT,BNB/USDT（使用英文逗号分隔）")
        raise typer.Exit(1)

    if timeframes and not validate_timeframes(timeframes):
        print(f"错误：时间周期格式错误: {timeframes}")
        print("支持的周期：15m, 30m, 1h, 4h, 1d（使用英文逗号分隔）")
        raise typer.Exit(1)

    if trading_mode and not validate_trading_mode(trading_mode):
        print(f"错误：交易模式错误: {trading_mode}")
        print("支持的模式：spot（现货）、futures（合约）、perpetual（永续合约）")
        raise typer.Exit(1)

    # 解析策略参数
    try:
        strategy_params = json.loads(params)
    except json.JSONDecodeError as e:
        print(f"策略参数解析失败: {params}")
        print(f"错误信息: {str(e)}")
        raise typer.Exit(1)

    # 加载策略
    strategy = load_strategy(strategy, strategy_params)

    # 从系统配置读取默认值
    system_config = get_system_config()
    default_trading_mode = system_config['default_trading_mode']
    default_timeframes = system_config['default_timeframes']

    # 使用命令行参数或默认值
    trading_mode = trading_mode or default_trading_mode
    timeframes = timeframes or ','.join(default_timeframes) if isinstance(default_timeframes, list) else default_timeframes

    # 解析货币对列表
    if symbols:
        symbols_list = [s.strip() for s in symbols.split(',')]
    else:
        symbols_list = ['BTCUSDT']

    # 解析时间周期列表
    timeframes_list = [t.strip() for t in timeframes.split(',')]

    output_file = output or os.path.join(backtest_results_dir, f"{strategy}_results.json")

    # 准备数据
    if data:
        print(f"从文件加载数据: {data}")
        try:
            df = pd.read_csv(data, index_col=0, parse_dates=True)

            # 确保数据包含必要的列
            required_columns = ['Open', 'High', 'Low', 'Close', 'Volume']
            for col in required_columns:
                if col not in df.columns:
                    print(f"数据文件缺少必要列: {col}")
                    raise typer.Exit(1)

        except Exception as e:
            print(f"加载数据文件失败: {data}")
            print(f"错误信息: {str(e)}")
            raise typer.Exit(1)

        # 使用文件数据
        data_dict = {symbols_list[0]: df}
    else:
        print("从数据库加载数据")
        try:
            data_dict = load_klines_from_db(
                symbols=symbols_list,
                timeframes=timeframes_list,
                time_range=time_range,
                trading_mode=trading_mode
            )

            if not data_dict:
                print("错误：未找到任何数据")
                raise typer.Exit(1)

            print(f"从数据库加载了 {len(data_dict)} 个数据集")

        except Exception as e:
            print(f"从数据库加载数据失败: {str(e)}")
            raise typer.Exit(1)

    print(f"货币对: {', '.join(symbols_list)}")
    print(f"时间周期: {', '.join(timeframes_list)}")
    print(f"交易模式: {trading_mode}")
    if time_range:
        print(f"时间范围: {time_range}")
    print()

    # 创建适配器
    adapter = VectorBacktestAdapter(strategy)

    # 运行回测
    print("运行回测...")
    results = {}

    for key, df in data_dict.items():
        print(f"回测: {key}")

        # 运行回测
        adapter_results = adapter.run_backtest(
            data={key: df},
            init_cash=init_cash,
            fees=fees,
            slippage=slippage
        )

        # adapter.run_backtest 返回 {symbol: result} 字典，提取单个结果
        result = adapter_results[key]

        # 添加额外信息
        result['symbol'], result['timeframe'] = key.split('_')
        result['trading_mode'] = trading_mode

        results[key] = result

    print("回测完成")
    print()

    # 输出结果
    output_results(results, output_format, output_file)

    print("=" * 70)
    print("回测成功完成！")
    print("=" * 70)


if __name__ == '__main__':
    app()
