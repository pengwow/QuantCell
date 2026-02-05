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
# logger.info(f"添加后端目录到路径: {backend_path}")
# 添加策略目录到路径
strategies_dir = os.path.join(backend_path, 'strategies')
# logger.info(f"添加策略目录到路径: {strategies_dir}")
if strategies_dir not in sys.path:
    sys.path.insert(0, strategies_dir)

backtest_results_dir = os.path.join(backend_path, 'backtest', 'results')
# logger.info(f"添加回测结果目录到路径: {backtest_results_dir}")

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
        # cash 现在是历史数组，取最后一个值作为最终现金
        final_cash = result['cash'][-1] if len(result['cash']) > 0 else 0.0
        init_cash = result['cash'][0] if len(result['cash']) > 0 else 0.0
        print(f"  初始资金: {init_cash:.2f}")
        print(f"  最终现金: {final_cash:.2f}")
        # positions 可能是 1D 或 2D 数组
        positions = result['positions']
        if positions.ndim > 1:
            final_position = positions[-1, 0] if len(positions) > 0 else 0.0
        else:
            final_position = positions[-1] if len(positions) > 0 else 0.0
        print(f"  最终持仓: {final_position:.4f}")
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
                    # 使用enumerate生成自增ID
                    for idx, order in enumerate(result['orders']):
                        # 获取时间戳
                        timestamp = order.get('timestamp')
                        if isinstance(timestamp, datetime):
                            timestamp_ms = int(timestamp.timestamp() * 1000)
                            formatted_time = timestamp.strftime('%Y-%m-%d %H:%M:%S')
                        elif isinstance(timestamp, str):
                            try:
                                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                                timestamp_ms = int(dt.timestamp() * 1000)
                                formatted_time = dt.strftime('%Y-%m-%d %H:%M:%S')
                            except:
                                timestamp_ms = 0
                                formatted_time = timestamp
                        else:
                            timestamp_ms = int(timestamp) if timestamp else 0
                            formatted_time = str(timestamp)

                        # 获取volume/size，确保不为null（策略可能使用size或volume字段）
                        volume = order.get('volume') or order.get('size')
                        if volume is None:
                            volume = 0.0
                        else:
                            volume = float(volume)

                        orders_serializable.append({
                            'order_id': str(idx + 1),  # 字符串格式的自增ID
                            'direction': order.get('direction', ''),
                            'price': float(order.get('price', 0)) if order.get('price') is not None else 0.0,
                            'volume': volume,
                            'status': order.get('status', 'filled'),  # 默认状态为filled
                            'timestamp': timestamp_ms,  # Unix时间戳（毫秒）
                            'formatted_time': formatted_time  # 格式化时间字符串
                        })

                # 序列化指标数据
                indicators_serializable = {}
                if 'indicators' in result and result['indicators']:
                    for key, value in result['indicators'].items():
                        # 处理嵌套字典（如策略保存的指标对象）
                        if isinstance(value, dict):
                            indicators_serializable[str(key)] = {
                                k: float(v) if isinstance(v, (np.floating, float)) else
                                  int(v) if isinstance(v, (np.integer, int)) else
                                  v.isoformat() if isinstance(v, datetime) else
                                  str(v)
                                for k, v in value.items()
                            }
                        elif isinstance(value, (np.floating, float)):
                            indicators_serializable[str(key)] = float(value)
                        elif isinstance(value, (np.integer, int)):
                            indicators_serializable[str(key)] = int(value)
                        elif isinstance(value, datetime):
                            indicators_serializable[str(key)] = value.isoformat()
                        else:
                            indicators_serializable[str(key)] = str(value)

                # 序列化策略交易数据
                strategy_trades_serializable = []
                if 'strategy_trades' in result and result['strategy_trades']:
                    for idx, trade in enumerate(result['strategy_trades']):
                        # 获取时间戳
                        timestamp = trade.get('timestamp')
                        if isinstance(timestamp, datetime):
                            timestamp_ms = int(timestamp.timestamp() * 1000)
                            formatted_time = timestamp.strftime('%Y-%m-%d %H:%M:%S')
                        elif isinstance(timestamp, str):
                            try:
                                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                                timestamp_ms = int(dt.timestamp() * 1000)
                                formatted_time = dt.strftime('%Y-%m-%d %H:%M:%S')
                            except:
                                timestamp_ms = 0
                                formatted_time = timestamp
                        else:
                            timestamp_ms = int(timestamp) if timestamp else 0
                            formatted_time = str(timestamp)

                        # 获取volume/size，确保不为null（策略可能使用size或volume字段）
                        volume = trade.get('volume') or trade.get('size')
                        if volume is None:
                            volume = 0.0
                        else:
                            volume = float(volume)

                        strategy_trades_serializable.append({
                            'trade_id': str(idx + 1),  # 字符串格式的自增ID
                            'direction': trade.get('direction', ''),
                            'price': float(trade.get('price', 0)) if trade.get('price') is not None else 0.0,
                            'volume': volume,
                            'timestamp': timestamp_ms,  # Unix时间戳（毫秒）
                            'formatted_time': formatted_time  # 格式化时间字符串
                        })

                # 构建结果字典
                result_dict = {
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
                
                # 添加指标元数据（如果存在）
                if 'indicators_info' in result:
                    result_dict['indicators_info'] = result['indicators_info']
                
                # 添加当前指标值（如果存在）
                if 'indicator_values' in result:
                    # 序列化指标值
                    indicator_values_serializable = {}
                    for key, value in result['indicator_values'].items():
                        if isinstance(value, dict):
                            indicator_values_serializable[key] = {
                                k: float(v) if isinstance(v, (np.floating, float)) else
                                  int(v) if isinstance(v, (np.integer, int)) else
                                  str(v) if v is not None else None
                                for k, v in value.items()
                            }
                        else:
                            indicator_values_serializable[key] = str(value) if value is not None else None
                    result_dict['indicator_values'] = indicator_values_serializable
                
                # 添加风险控制信息（如果存在）
                if 'risk_control' in result:
                    result_dict['risk_control'] = result['risk_control']
                
                serializable_results[symbol] = result_dict

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
    params: Annotated[str, typer.Option("--params", "-p", help='策略参数（JSON格式），例如：\'{"grid_count": 20, "position_size": 0.01}\'')] = "{}",
    data: Annotated[Optional[str], typer.Option("--data", "-d", help="数据文件路径（CSV格式），如果不指定则从数据库加载")] = None,
    init_cash: Annotated[float, typer.Option("--init-cash", help="初始资金")] = 100000.0,
    fees: Annotated[float, typer.Option("--fees", help="手续费率")] = 0.001,
    slippage: Annotated[float, typer.Option("--slippage", help="滑点")] = 0.0001,
    output_format: Annotated[str, typer.Option("--output-format", "-f", help="输出格式：json 或 csv")] = "json",
    output: Annotated[Optional[str], typer.Option("--output", "-o", help="输出文件路径，如果不指定则自动生成文件名")] = None,
    time_range: Annotated[Optional[str], typer.Option("--time-range", help="回测时间范围（格式：YYYYMMDD-YYYYMMDD），例如：20240101-20241231")] = None,
    symbols: Annotated[Optional[str], typer.Option("--symbols", help="货币对列表（多个货币对使用英文逗号分隔），例如：BTCUSDT,ETHUSDT,BNBUSDT")] = None,
    timeframes: Annotated[Optional[str], typer.Option("--timeframes", help="时间周期列表（多个周期使用英文逗号分隔），支持：15m,30m,1h,4h,1d，例如：15m,30m,1h")] = None,
    trading_mode: Annotated[Optional[str], typer.Option("--trading-mode", help="交易模式（spot=现货，futures=合约，perpetual=永续合约），默认从系统配置读取")] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="显示详细日志")] = False,
    save_to_db: Annotated[bool, typer.Option("--save-to-db/--no-save-to-db", help="是否将回测结果保存到数据库")] = False
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

    # 保存策略名称用于生成文件名
    strategy_name = strategy

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

    # 生成文件名：策略名称_时间戳.json
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output or os.path.join(backtest_results_dir, f"{strategy_name}_{timestamp}_results.json")

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

            print(f"从数据库加载了 {[f'{k}: {len(v)}' for k, v in data_dict.items()]} 个数据集")
            
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

    # 输出结果
    output_results(results, output_format, output_file)

    # 保存到数据库
    if save_to_db:
        print("\n正在保存结果到数据库...")
        try:
            from collector.db.database import init_database_config, SessionLocal
            from collector.db.models import BacktestTask, BacktestResult
            from sqlalchemy import func

            # 初始化数据库
            init_database_config()
            db = SessionLocal()

            try:
                # 为每个交易对创建任务和结果记录
                for key, result in results.items():
                    symbol, timeframe = key.split('_')

                    # 生成任务ID
                    task_id = f"{strategy_name}_{symbol}_{timeframe}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

                    # 创建回测任务
                    backtest_config = {
                        'symbols': [symbol],
                        'interval': timeframe,
                        'start_time': time_range.split('-')[0] if time_range else None,
                        'end_time': time_range.split('-')[1] if time_range else None,
                        'initial_cash': init_cash,
                        'commission': fees,
                        'slippage': slippage,
                        'trading_mode': trading_mode,
                        'strategy_params': strategy_params
                    }

                    task = BacktestTask(
                        id=task_id,
                        strategy_name=strategy_name,
                        backtest_config=json.dumps(backtest_config, ensure_ascii=False),
                        status='completed',
                        completed_at=func.now()
                    )
                    db.add(task)

                    # 准备结果数据
                    metrics = result.get('metrics', {})
                    trades = result.get('trades', [])
                    equity_curve = result.get('equity_curve', [])
                    strategy_data = result.get('strategy_data', [])

                    # 创建回测结果
                    result_record = BacktestResult(
                        id=f"{task_id}_result",
                        task_id=task_id,
                        strategy_name=strategy_name,
                        symbol=symbol,
                        metrics=json.dumps(metrics, ensure_ascii=False, default=str),
                        trades=json.dumps(trades, ensure_ascii=False, default=str),
                        equity_curve=json.dumps(equity_curve, ensure_ascii=False, default=str),
                        strategy_data=json.dumps(strategy_data, ensure_ascii=False, default=str)
                    )
                    db.add(result_record)

                    # 更新任务的result_id
                    task.result_id = result_record.id

                    print(f"  ✓ 已保存 {symbol} {timeframe} 的回测结果")

                # 提交事务
                db.commit()
                print(f"\n✓ 成功将 {len(results)} 个回测结果保存到数据库")

            except Exception as e:
                db.rollback()
                print(f"✗ 保存到数据库失败: {str(e)}")
                logger.exception("保存回测结果到数据库失败")
            finally:
                db.close()

        except ImportError as e:
            print(f"✗ 无法导入数据库模块: {str(e)}")
            print("  请确保数据库配置正确")
        except Exception as e:
            print(f"✗ 保存到数据库时发生错误: {str(e)}")
            logger.exception("保存回测结果到数据库失败")

    print("=" * 70)
    print("回测成功完成！")
    print("=" * 70)


@app.command()
def plot(
    input_file: Annotated[str, typer.Argument(help="JSON格式的回测结果文件路径")],
    output: Annotated[Optional[str], typer.Option("--output", "-o", help="输出图片文件路径，默认自动生成")] = None,
    show: Annotated[bool, typer.Option("--show/--no-show", help="是否显示图表")] = True,
    plot_type: Annotated[str, typer.Option("--plot-type", "-t", help="图表类型：all(全部), equity(资金曲线), trades(交易分布), metrics(指标统计)")] = "all"
):
    """
    加载回测结果并绘制可视化图表
    
    从JSON文件加载回测结果，生成资金曲线、交易分布等可视化图表
    
    示例:
      # 绘制所有图表
      python backtest_cli.py plot results.json
      
      # 只绘制资金曲线并保存到指定文件
      python backtest_cli.py plot results.json --plot-type equity -o equity_chart.png
      
      # 不显示图表，只保存文件
      python backtest_cli.py plot results.json --no-show -o chart.png
    """
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from datetime import datetime
    
    print("=" * 70)
    print("加载回测结果并绘制图表")
    print("=" * 70)
    print()
    
    # 验证文件路径
    input_path = Path(input_file)
    if not input_path.exists():
        print(f"错误：文件不存在: {input_file}", err=True)
        raise typer.Exit(1)
    
    # 验证文件格式
    if not input_file.lower().endswith('.json'):
        print(f"错误：仅支持JSON格式文件", err=True)
        raise typer.Exit(1)
    
    # 加载JSON文件
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            results = json.load(f)
    except json.JSONDecodeError as e:
        print(f"错误：JSON文件解析失败: {str(e)}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        print(f"错误：读取文件失败: {str(e)}", err=True)
        raise typer.Exit(1)
    
    print(f"✓ 成功加载回测结果文件: {input_file}")
    print(f"  包含 {len(results)} 个交易对的数据")
    print()
    
    # 为每个交易对生成图表
    for symbol_key, result in results.items():
        print(f"正在生成 {symbol_key} 的图表...")
        
        # 获取数据
        symbol = result.get('symbol', symbol_key)
        metrics = result.get('metrics', {})
        trades = result.get('trades', [])
        equity_curve = result.get('equity_curve', [])
        indicators = result.get('indicators', {})
        
        # 如果没有trades但有orders，使用orders作为交易记录
        if not trades and 'orders' in result:
            orders = result['orders']
            # 将orders转换为trades格式
            trades = []
            for i in range(0, len(orders) - 1, 2):
                if i + 1 < len(orders):
                    entry = orders[i]
                    exit = orders[i + 1]
                    entry_price = float(entry.get('price', 0))
                    exit_price = float(exit.get('price', 0))
                    size = float(entry.get('size', 0.1))
                    pnl = (exit_price - entry_price) * size
                    return_pct = ((exit_price - entry_price) / entry_price * 100) if entry_price > 0 else 0
                    
                    trades.append({
                        'trade_id': i // 2,
                        'entry_time': entry.get('timestamp', ''),
                        'exit_time': exit.get('timestamp', ''),
                        'entry_price': entry_price,
                        'exit_price': exit_price,
                        'size': size,
                        'pnl': pnl,
                        'return_pct': return_pct,
                        'direction': entry.get('direction', 'buy'),
                        'PnL': pnl,
                        'ReturnPct': return_pct
                    })
        
        # 如果没有equity_curve，尝试从orders构建
        if not equity_curve and 'orders' in result:
            # 从初始资金开始，根据交易计算权益变化
            init_cash = 100000.0
            cash = init_cash
            position = 0  # 持仓数量
            entry_price = 0  # 入场价格
            equity_curve = []
            max_equity = init_cash  # 用于计算回撤

            for i, order in enumerate(result['orders']):
                price = float(order.get('price', 0))
                direction = order.get('direction', '')
                # 获取交易数量，优先使用volume，其次size，默认0.1
                size = float(order.get('volume') or order.get('size') or 0.1)

                if direction in ['buy', 'long']:
                    # 买入：减少现金，增加持仓
                    cost = price * size
                    cash -= cost
                    position = size
                    entry_price = price
                elif direction in ['sell', 'short']:
                    # 卖出：增加现金，清空持仓，计算盈亏
                    revenue = price * position
                    pnl = (price - entry_price) * position if entry_price > 0 else 0
                    cash += revenue
                    position = 0
                    entry_price = 0

                # 计算当前权益 = 现金 + 持仓市值
                position_value = position * price if position > 0 else 0
                current_equity = cash + position_value

                # 更新最大权益
                if current_equity > max_equity:
                    max_equity = current_equity

                # 计算回撤
                drawdown = max_equity - current_equity
                drawdown_pct = (drawdown / max_equity * 100) if max_equity > 0 else 0

                timestamp = order.get('timestamp', '')
                if isinstance(timestamp, str):
                    try:
                        dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                        ts_ms = int(dt.timestamp() * 1000)
                    except:
                        ts_ms = i
                else:
                    ts_ms = int(timestamp) if timestamp else i

                equity_curve.append({
                    'timestamp': ts_ms,
                    'datetime': timestamp if isinstance(timestamp, str) else str(timestamp),
                    'equity': current_equity,
                    'cash': cash,
                    'position_value': position_value,
                    'drawdown': drawdown,
                    'drawdown_pct': drawdown_pct
                })
        
        # 获取盈亏统计数据
        pnl_stats = result.get('pnl_stats', {})
        
        # 根据plot_type决定生成哪些图表
        if plot_type in ['all', 'equity']:
            _plot_equity_curve(symbol, equity_curve, trades, metrics, output, show, pnl_stats)
        
        if plot_type in ['all', 'trades']:
            _plot_trade_distribution(symbol, trades, metrics, output, show)
        
        if plot_type in ['all', 'metrics']:
            _plot_metrics_summary(symbol, metrics, output, show)
    
    print()
    print("=" * 70)
    print("图表生成完成！")
    print("=" * 70)


def _setup_chinese_font():
    """设置matplotlib中文字体"""
    import matplotlib.pyplot as plt
    import matplotlib.font_manager as fm
    import platform
    
    system = platform.system()
    
    # 尝试查找系统中文字体
    chinese_fonts = {
        'Darwin': ['/System/Library/Fonts/PingFang.ttc',  # macOS 苹方字体
                   '/System/Library/Fonts/STHeiti Light.ttc',
                   '/Library/Fonts/Arial Unicode.ttf'],
        'Linux': ['/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',  # Linux 文泉驿
                  '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',
                  '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'],
        'Windows': ['C:/Windows/Fonts/simhei.ttf',  # Windows 黑体
                    'C:/Windows/Fonts/simsun.ttc',  # 宋体
                    'C:/Windows/Fonts/msyh.ttc']    # 微软雅黑
    }
    
    font_found = False
    for font_path in chinese_fonts.get(system, []):
        if os.path.exists(font_path):
            try:
                font_prop = fm.FontProperties(fname=font_path)
                plt.rcParams['font.family'] = font_prop.get_name()
                plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题
                font_found = True
                break
            except:
                continue
    
    # 如果没有找到系统字体，尝试使用matplotlib默认字体
    if not font_found:
        try:
            # 尝试使用DejaVu Sans（支持部分中文）
            plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial Unicode MS', 'SimHei', 'sans-serif']
            plt.rcParams['axes.unicode_minus'] = False
        except:
            pass
    
    return font_found


def _plot_equity_curve(symbol: str, equity_curve: list, trades: list, metrics: dict, output: Optional[str], show: bool, pnl_stats: dict = None):
    """绘制资金曲线图 - 标准折线图，仅显示总资金权益曲线和初始资金参考线"""
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates

    # 设置中文字体
    _setup_chinese_font()

    if not equity_curve:
        print(f"  警告: {symbol} 没有资金曲线数据")
        return

    # 创建单个子图（标准折线图）
    fig, ax = plt.subplots(1, 1, figsize=(12, 6))

    # 准备数据
    timestamps = []
    equities = []

    for point in equity_curve:
        if isinstance(point, dict):
            timestamps.append(point.get('timestamp', 0))
            equities.append(point.get('equity', 0))

    if not timestamps or not equities:
        print(f"  警告: {symbol} 资金曲线数据格式不正确")
        return

    # 转换时间戳为日期
    dates = [datetime.fromtimestamp(ts / 1000) if ts > 1e10 else datetime.fromtimestamp(ts)
             for ts in timestamps]

    # 绘制总资金权益曲线（标准折线图）
    ax.plot(dates, equities, label='总资金权益', color='#2196F3', linewidth=1.5, linestyle='-')

    # 添加初始资金参考线
    initial_cash = equities[0] if equities else 100000
    ax.axhline(y=initial_cash, color='gray', linestyle='--', alpha=0.7, linewidth=1, label='初始资金')

    # 设置标题
    title = f'{symbol} 资金权益曲线'
    if pnl_stats:
        realized = pnl_stats.get('realized_pnl', 0)
        unrealized = pnl_stats.get('unrealized_pnl', 0)
        total_pnl = realized + unrealized
        title += f'\n实际盈亏: {realized:.2f} | 浮动盈亏: {unrealized:.2f} | 总盈亏: {total_pnl:.2f}'
    ax.set_title(title, fontsize=12, fontweight='bold')

    # 设置坐标轴标签
    ax.set_xlabel('时间', fontsize=10)
    ax.set_ylabel('资金权益', fontsize=10)

    # 添加图例
    ax.legend(loc='best', fontsize=9)

    # 添加网格（轻微）
    ax.grid(True, alpha=0.3, linestyle=':')

    # 设置x轴日期格式
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)

    # 调整布局
    plt.tight_layout()

    # 保存图片
    if output:
        output_path = output if output.endswith('.png') else f"{output}.png"
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"  ✓ 资金曲线图已保存: {output_path}")
    else:
        output_path = f"{symbol}_equity_curve.png"
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"  ✓ 资金曲线图已保存: {output_path}")

    if show:
        plt.show()
    else:
        plt.close()


def _plot_trade_distribution(symbol: str, trades: list, metrics: dict, output: Optional[str], show: bool):
    """绘制交易分布图"""
    import matplotlib.pyplot as plt
    
    # 设置中文字体
    _setup_chinese_font()
    
    if not trades:
        print(f"  警告: {symbol} 没有交易记录")
        return
    
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(f'{symbol} 交易分析', fontsize=16, fontweight='bold')
    
    # 提取盈亏数据
    pnls = []
    returns = []
    directions = []
    
    for trade in trades:
        if isinstance(trade, dict):
            pnl = trade.get('PnL') or trade.get('pnl') or trade.get('profit') or 0
            ret = trade.get('ReturnPct') or trade.get('return_pct') or trade.get('return') or 0
            direction = trade.get('Direction') or trade.get('direction') or 'long'
            
            pnls.append(float(pnl))
            returns.append(float(ret))
            directions.append(direction)
    
    if not pnls:
        print(f"  警告: {symbol} 没有有效的盈亏数据")
        plt.close()
        return
    
    # 1. 盈亏分布直方图
    ax1 = axes[0, 0]
    colors = ['green' if p > 0 else 'red' for p in pnls]
    ax1.bar(range(len(pnls)), pnls, color=colors, alpha=0.7)
    ax1.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
    ax1.set_title('单笔盈亏分布', fontsize=12)
    ax1.set_xlabel('交易序号')
    ax1.set_ylabel('盈亏')
    ax1.grid(True, alpha=0.3)
    
    # 2. 收益率分布
    ax2 = axes[0, 1]
    ax2.hist(returns, bins=20, color='blue', alpha=0.7, edgecolor='black')
    ax2.axvline(x=0, color='red', linestyle='--', linewidth=2)
    ax2.set_title('收益率分布', fontsize=12)
    ax2.set_xlabel('收益率 (%)')
    ax2.set_ylabel('频次')
    ax2.grid(True, alpha=0.3)
    
    # 3. 多空对比
    ax3 = axes[1, 0]
    long_count = sum(1 for d in directions if d.lower() in ['long', 'buy', '多单'])
    short_count = sum(1 for d in directions if d.lower() in ['short', 'sell', '空单'])
    
    if long_count > 0 or short_count > 0:
        ax3.bar(['多单', '空单'], [long_count, short_count], color=['green', 'red'], alpha=0.7)
        ax3.set_title('多空交易次数', fontsize=12)
        ax3.set_ylabel('交易次数')
        ax3.grid(True, alpha=0.3, axis='y')
    else:
        ax3.text(0.5, 0.5, '无方向数据', ha='center', va='center', transform=ax3.transAxes)
    
    # 4. 累计盈亏
    ax4 = axes[1, 1]
    cumulative_pnl = [sum(pnls[:i+1]) for i in range(len(pnls))]
    ax4.plot(cumulative_pnl, color='blue', linewidth=2)
    ax4.fill_between(range(len(cumulative_pnl)), cumulative_pnl, 0, 
                     where=[x > 0 for x in cumulative_pnl], alpha=0.3, color='green')
    ax4.fill_between(range(len(cumulative_pnl)), cumulative_pnl, 0, 
                     where=[x <= 0 for x in cumulative_pnl], alpha=0.3, color='red')
    ax4.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
    ax4.set_title('累计盈亏', fontsize=12)
    ax4.set_xlabel('交易序号')
    ax4.set_ylabel('累计盈亏')
    ax4.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    # 保存图片
    if output:
        output_path = output.replace('.png', '_trades.png') if output.endswith('.png') else f"{output}_trades.png"
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"  ✓ 交易分布图已保存: {output_path}")
    else:
        output_path = f"{symbol}_trade_distribution.png"
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"  ✓ 交易分布图已保存: {output_path}")
    
    if show:
        plt.show()
    else:
        plt.close()


def _plot_metrics_summary(symbol: str, metrics: dict, output: Optional[str], show: bool):
    """绘制指标汇总图"""
    import matplotlib.pyplot as plt
    
    # 设置中文字体
    _setup_chinese_font()
    
    fig, ax = plt.subplots(figsize=(12, 8))
    fig.suptitle(f'{symbol} 回测指标汇总', fontsize=16, fontweight='bold')
    
    # 准备指标数据
    metric_names = []
    metric_values = []
    
    # 关键指标映射
    key_metrics = {
        'total_return': '总收益率 (%)',
        'total_pnl': '总盈亏',
        'sharpe_ratio': '夏普比率',
        'max_drawdown': '最大回撤 (%)',
        'win_rate': '胜率 (%)',
        'profit_factor': '盈亏比',
        'total_trades': '总交易次数',
        'avg_trade': '平均收益',
        'final_equity': '最终权益',
        'return_pct': '收益率 (%)',
        'Return [%]': '收益率 (%)',
        'Sharpe Ratio': '夏普比率',
        'Max. Drawdown [%]': '最大回撤 (%)',
        'Win Rate [%]': '胜率 (%)',
        'Profit Factor': '盈亏比',
        '# Trades': '总交易次数'
    }
    
    for key, label in key_metrics.items():
        if key in metrics:
            value = metrics[key]
            # 处理百分比值
            if isinstance(value, (int, float)):
                metric_names.append(label)
                metric_values.append(float(value))
    
    if not metric_names:
        ax.text(0.5, 0.5, '无指标数据', ha='center', va='center', transform=ax.transAxes, fontsize=14)
    else:
        # 绘制水平条形图
        colors = ['green' if v > 0 else 'red' if v < 0 else 'gray' for v in metric_values]
        bars = ax.barh(metric_names, metric_values, color=colors, alpha=0.7)
        
        # 在条形上添加数值标签
        for i, (bar, value) in enumerate(zip(bars, metric_values)):
            width = bar.get_width()
            ax.text(width, bar.get_y() + bar.get_height()/2, 
                   f'{value:.4f}' if abs(value) < 10 else f'{value:.2f}',
                   ha='left' if width >= 0 else 'right', va='center', fontsize=10)
        
        ax.axvline(x=0, color='black', linestyle='-', linewidth=0.5)
        ax.set_xlabel('数值', fontsize=12)
        ax.grid(True, alpha=0.3, axis='x')
    
    plt.tight_layout()
    
    # 保存图片
    if output:
        output_path = output.replace('.png', '_metrics.png') if output.endswith('.png') else f"{output}_metrics.png"
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"  ✓ 指标汇总图已保存: {output_path}")
    else:
        output_path = f"{symbol}_metrics_summary.png"
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"  ✓ 指标汇总图已保存: {output_path}")
    
    if show:
        plt.show()
    else:
        plt.close()


if __name__ == '__main__':
    app()
