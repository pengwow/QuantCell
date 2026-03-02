# -*- coding: utf-8 -*-
"""
回测CLI命令入口

提供Typer命令定义，调用cli_core模块实现具体功能
支持多种回测引擎：默认引擎和事件驱动引擎
"""

import json
import os
import sys
import datetime as dt
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

import typer
from loguru import logger
from typing_extensions import Annotated

# 创建Typer应用
app = typer.Typer(
    name="backtest",
    help="QUANTCELL 回测命令行工具",
    epilog="""
示例:
  # 使用默认参数运行策略
  python backtest_cli.py run --strategy sma_cross_strategy

  # 指定策略参数
  python backtest_cli.py run --strategy sma_cross_strategy --params '{"fast_period": 10, "slow_period": 30}'

  # 指定时间范围和货币对
  python backtest_cli.py run --strategy sma_cross_strategy --time-range 20240101-20241231 --symbols BTCUSDT,ETHUSDT

  # 使用自选组合
  python backtest_cli.py run --strategy sma_cross_strategy --pool 我的自选组合

  # 指定时间周期和交易模式
  python backtest_cli.py run --strategy sma_cross_strategy --timeframes 15m,1h --trading-mode futures

  # 保存结果到数据库
  python backtest_cli.py run --strategy sma_cross_strategy --pool 自选全部 --save-to-db

  # 绘制回测结果图表
  python backtest_cli.py plot results.json

  # 使用事件驱动引擎运行回测
  python backtest_cli.py run --strategy sma_cross_nautilus --engine event --init-cash 100000 --fees 0.001

  # 使用事件驱动引擎指定基础货币和杠杆
  python backtest_cli.py run --strategy sma_cross_nautilus --engine event --base-currency USDT --leverage 2
    """
)


# 定义引擎类型枚举
class EngineType(str, Enum):
    """回测引擎类型"""
    DEFAULT = "default"
    EVENT = "event"


def validate_engine_type(engine: str) -> bool:
    """
    验证引擎类型是否有效
    
    参数：
        engine: 引擎类型字符串
        
    返回：
        bool: 是否有效
    """
    valid_engines = ["default", "event"]
    return engine.lower() in valid_engines


@app.command()
def run(
    strategy: Annotated[str, typer.Option("--strategy", "-s", help="策略文件名（不带.py后缀）")],
    params: Annotated[str, typer.Option("--params", "-p", help='策略参数（JSON格式）')] = "{}",
    data: Annotated[Optional[str], typer.Option("--data", "-d", help="数据文件路径（CSV格式")] = None,
    init_cash: Annotated[float, typer.Option("--init-cash", help="初始资金")] = 100000.0,
    fees: Annotated[float, typer.Option("--fees", help="手续费率")] = 0.001,
    slippage: Annotated[float, typer.Option("--slippage", help="滑点")] = 0.0001,
    output_format: Annotated[str, typer.Option("--output-format", "-f", help="输出格式：json 或 csv")] = "json",
    output: Annotated[Optional[str], typer.Option("--output", "-o", help="输出文件路径")] = None,
    time_range: Annotated[Optional[str], typer.Option("--time-range", help="回测时间范围（YYYYMMDD-YYYYMMDD）")] = None,
    symbols: Annotated[Optional[str], typer.Option("--symbols", help="货币对列表（逗号分隔）")] = None,
    pool: Annotated[Optional[str], typer.Option("--pool", help="自选组合名称")] = None,
    timeframes: Annotated[Optional[str], typer.Option("--timeframes", help="时间周期列表（逗号分隔）")] = None,
    trading_mode: Annotated[Optional[str], typer.Option("--trading-mode", help="交易模式（spot/futures/perpetual）")] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="显示详细日志")] = False,
    detail: Annotated[bool, typer.Option("--detail", help="显示详细交易输出（买入/卖出/持仓更新等）")] = False,
    save_to_db: Annotated[bool, typer.Option("--save-to-db/--no-save-to-db", help="是否保存到数据库")] = False,
    auto_download: Annotated[bool, typer.Option("--auto-download/--no-auto-download", help="是否自动下载缺失数据")] = True,
    ignore_missing: Annotated[bool, typer.Option("--ignore-missing", help="忽略数据缺失，允许不完整数据继续回测")] = False,
    no_progress: Annotated[bool, typer.Option("--no-progress", help="不显示进度条")] = False,
    engine: Annotated[EngineType, typer.Option("--engine", "-e", help="回测引擎类型（default/event）")] = EngineType.DEFAULT,
    base_currency: Annotated[str, typer.Option("--base-currency", help="基础货币代码（仅事件驱动引擎）")] = "USDT",
    leverage: Annotated[float, typer.Option("--leverage", help="杠杆倍数（仅事件驱动引擎）")] = 1.0,
    venue: Annotated[str, typer.Option("--venue", help="交易所名称（仅事件驱动引擎）")] = "SIM",
):
    """
    运行回测
    
    支持两种回测引擎：
    - default: 默认回测引擎，使用QuantCell原生回测框架
    - event: 事件驱动引擎，使用高性能事件驱动回测框架
    """
    # 延迟导入，避免在--help时触发日志初始化
    from backtest.cli_core import (
        CLICore, get_system_config, get_symbols_from_data_pool,
        DataPreparationError, StrategyLoadError, BacktestExecutionError,
        DownloadFailureType
    )
    from utils.validation import (
        validate_time_range, validate_symbols, validate_timeframes, 
        validate_trading_mode, parse_symbols, parse_timeframes
    )
    from utils.logger import setup_logger, get_default_log_file
    
    # 设置日志
    log_file = get_default_log_file() if verbose else None
    setup_logger(level="DEBUG" if verbose else "INFO", log_file=log_file, simple_console=not verbose)
    
    print("=" * 70)
    print("开始回测")
    print(f"引擎类型: {engine.value}")
    print("=" * 70)
    print()
    
    # 验证参数
    if time_range and not validate_time_range(time_range):
        print(f"错误：时间范围格式错误: {time_range}")
        print("正确格式：YYYYMMDD-YYYYMMDD，例如：20240101-20241231")
        raise typer.Exit(1)
    
    if symbols and not validate_symbols(symbols):
        print(f"错误：货币对格式错误")
        raise typer.Exit(1)
    
    if timeframes and not validate_timeframes(timeframes):
        print(f"错误：时间周期格式错误: {timeframes}")
        print("支持的周期：15m, 30m, 1h, 4h, 1d")
        raise typer.Exit(1)
    
    if trading_mode and not validate_trading_mode(trading_mode):
        print(f"错误：交易模式错误: {trading_mode}")
        print("支持的模式：spot（现货）、futures（合约）、perpetual（永续合约）")
        raise typer.Exit(1)
    
    # 检查是否同时指定了 symbols 和 pool
    if symbols and pool:
        print("错误：不能同时指定 --symbols 和 --pool 参数")
        raise typer.Exit(1)
    
    # 解析策略参数
    try:
        strategy_params = json.loads(params)
    except json.JSONDecodeError as e:
        print(f"策略参数解析失败: {e}")
        raise typer.Exit(1)
    
    # 保存策略名称
    strategy_name = strategy
    
    # 根据引擎类型选择回测执行方式
    if engine == EngineType.EVENT:
        # 使用事件驱动引擎
        return _run_event_backtest(
            strategy_name=strategy_name,
            strategy_params=strategy_params,
            data_path=data,
            init_cash=init_cash,
            fees=fees,
            slippage=slippage,
            output_format=output_format,
            output=output,
            time_range=time_range,
            symbols=symbols,
            pool=pool,
            timeframes=timeframes,
            trading_mode=trading_mode,
            verbose=verbose,
            detail=detail,
            save_to_db=save_to_db,
            auto_download=auto_download,
            ignore_missing=ignore_missing,
            no_progress=no_progress,
            base_currency=base_currency,
            leverage=leverage,
            venue=venue,
        )
    else:
        # 使用默认引擎
        return _run_default_backtest(
            strategy_name=strategy_name,
            strategy_params=strategy_params,
            data_path=data,
            init_cash=init_cash,
            fees=fees,
            slippage=slippage,
            output_format=output_format,
            output=output,
            time_range=time_range,
            symbols=symbols,
            pool=pool,
            timeframes=timeframes,
            trading_mode=trading_mode,
            verbose=verbose,
            detail=detail,
            save_to_db=save_to_db,
            auto_download=auto_download,
            ignore_missing=ignore_missing,
            no_progress=no_progress,
        )


def _run_default_backtest(
    strategy_name: str,
    strategy_params: dict,
    data_path: Optional[str],
    init_cash: float,
    fees: float,
    slippage: float,
    output_format: str,
    output: Optional[str],
    time_range: Optional[str],
    symbols: Optional[str],
    pool: Optional[str],
    timeframes: Optional[str],
    trading_mode: Optional[str],
    verbose: bool,
    detail: bool,
    save_to_db: bool,
    auto_download: bool,
    ignore_missing: bool,
    no_progress: bool,
) -> None:
    """
    使用默认引擎运行回测
    
    这是原有的回测逻辑，使用QuantCell原生回测框架
    """
    # 延迟导入
    from backtest.cli_core import (
        CLICore, get_system_config, get_symbols_from_data_pool,
        DataPreparationError, StrategyLoadError, BacktestExecutionError,
        DownloadFailureType
    )
    from backtest.result_analysis import output_results
    from utils.validation import parse_symbols, parse_timeframes
    
    # 创建CLI核心
    cli_core = CLICore(verbose=verbose, detail=detail)
    
    # 加载策略
    try:
        print(f"加载策略: {strategy_name}")
        strategy_obj = cli_core.load_strategy(strategy_name, strategy_params)
    except StrategyLoadError as e:
        print(f"错误：{e}")
        raise typer.Exit(1)
    
    # 从系统配置读取默认值
    system_config = get_system_config()
    default_trading_mode = system_config['default_trading_mode']
    default_timeframes = system_config['default_timeframes']
    
    # 使用命令行参数或默认值
    trading_mode = trading_mode or default_trading_mode
    timeframes = timeframes or ','.join(default_timeframes) if isinstance(default_timeframes, list) else default_timeframes
    
    # 解析货币对列表
    symbols_list = []
    if pool:
        print(f"从自选组合 '{pool}' 获取货币对...")
        try:
            symbols_list = get_symbols_from_data_pool(pool)
            if not symbols_list:
                print(f"错误：自选组合 '{pool}' 中没有货币对")
                raise typer.Exit(1)
            print(f"成功获取 {len(symbols_list)} 个货币对: {', '.join(symbols_list)}")
        except ValueError as e:
            print(f"错误：{e}")
            raise typer.Exit(1)
    elif symbols:
        symbols_list = parse_symbols(symbols)
    else:
        symbols_list = ['BTCUSDT']
    
    # 解析时间周期列表
    timeframes_list = parse_timeframes(timeframes)
    
    # 生成输出文件名
    if output is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = str(cli_core.results_dir / f"{strategy_name}_{timestamp}_results.{output_format}")
    else:
        output_file = output
    
    # 准备数据
    if data_path:
        # 从文件加载数据
        print(f"从文件加载数据: {data_path}")
        try:
            import pandas as pd
            df = pd.read_csv(data_path, index_col=0, parse_dates=True)
            required_columns = ['Open', 'High', 'Low', 'Close', 'Volume']
            for col in required_columns:
                if col not in df.columns:
                    print(f"数据文件缺少必要列: {col}")
                    raise typer.Exit(1)
            data_dict = {symbols_list[0]: df}
        except Exception as e:
            print(f"加载数据文件失败: {e}")
            raise typer.Exit(1)
    else:
        # 从数据库加载数据
        print("从数据库加载数据...")
        try:
            data_dict, download_results = cli_core.prepare_data(
                symbols=symbols_list,
                timeframes=timeframes_list,
                time_range=time_range,
                trading_mode=trading_mode or 'spot',
                auto_download=auto_download,
                ignore_missing=ignore_missing,
                show_progress=not no_progress
            )
            
            # 报告下载结果摘要
            failed_results = [r for r in download_results if not r.success]
            no_data_failures = [r for r in failed_results
                              if r.failure_type == DownloadFailureType.NO_DATA_AVAILABLE]

            # 收集数据不完整的警告信息
            incomplete_results = [r for r in download_results if r.success and r.is_incomplete]

            if no_data_failures:
                print(f"\n⚠️ 以下 {len(no_data_failures)} 个货币对数据源无可用数据，已跳过:")
                for result in no_data_failures:
                    print(f"  - {result.symbol} {result.timeframe}")

            # 显示数据不完整警告
            if incomplete_results:
                print(f"\n⚠️ 以下 {len(incomplete_results)} 个货币对数据不完整:")
                for result in incomplete_results:
                    missing_pct = 100.0 - result.coverage_percent
                    print(f"  - {result.symbol} {result.timeframe}: 覆盖率 {result.coverage_percent:.1f}%，缺失 {missing_pct:.1f}%")
                    if result.warnings:
                        for warning in result.warnings:
                            print(f"    • {warning}")
                if ignore_missing:
                    print(f"  已根据 --ignore-missing 参数继续回测")

            if not data_dict:
                print("\n✗ 没有成功加载任何数据，回测无法继续")
                raise typer.Exit(1)

            print(f"\n✓ 成功加载 {len(data_dict)} 个货币对的数据")

            # 保存失败信息用于后续报告
            download_failures = [
                {
                    'symbol': r.symbol,
                    'timeframe': r.timeframe,
                    'failure_type': r.failure_type.value if r.failure_type else 'unknown',
                    'reason': r.failure_reason
                }
                for r in failed_results
            ]

            # 保存数据不完整信息用于后续报告
            incomplete_data_info = [
                {
                    'symbol': r.symbol,
                    'timeframe': r.timeframe,
                    'is_incomplete': r.is_incomplete,
                    'coverage_percent': r.coverage_percent,
                    'missing_percent': 100.0 - r.coverage_percent,
                    'warnings': r.warnings
                }
                for r in incomplete_results
            ]
                
        except DataPreparationError as e:
            print(f"错误：{e}")
            raise typer.Exit(1)
    
    print(f"\n货币对: {', '.join(symbols_list)}")
    print(f"时间周期: {', '.join(timeframes_list)}")
    print(f"交易模式: {trading_mode}")
    if time_range:
        print(f"时间范围: {time_range}")
    print()
    
    # 执行回测
    try:
        config = {
            'init_cash': init_cash,
            'fees': fees,
            'slippage': slippage,
            'trading_mode': trading_mode,
            'time_range': time_range,
            'strategy_params': strategy_params
        }
        
        results = cli_core.run_backtest(
            strategy=strategy_obj,
            data_dict=data_dict,
            config=config,
            show_progress=not no_progress
        )
        
        # 如果有下载失败信息，添加到结果中
        if 'download_failures' in locals() and download_failures:
            results['_download_failures'] = download_failures

        # 如果有数据不完整信息，添加到结果中
        if 'incomplete_data_info' in locals() and incomplete_data_info:
            results['_incomplete_data_info'] = incomplete_data_info

    except BacktestExecutionError as e:
        print(f"错误：{e}")
        raise typer.Exit(1)
    
    # 输出结果
    output_results(results, output_format, output_file)
    
    # 保存到数据库
    if save_to_db:
        print("\n正在保存结果到数据库...")
        if cli_core.save_to_database(results, strategy_name, config):
            print("✓ 结果已成功保存到数据库")
        else:
            print("✗ 保存到数据库失败")
    
    print("\n" + "=" * 70)
    print("回测成功完成！")
    print("=" * 70)


def _run_event_backtest(
    strategy_name: str,
    strategy_params: dict,
    data_path: Optional[str],
    init_cash: float,
    fees: float,
    slippage: float,
    output_format: str,
    output: Optional[str],
    time_range: Optional[str],
    symbols: Optional[str],
    pool: Optional[str],
    timeframes: Optional[str],
    trading_mode: Optional[str],
    verbose: bool,
    detail: bool,
    save_to_db: bool,
    auto_download: bool,
    ignore_missing: bool,
    no_progress: bool,
    base_currency: str,
    leverage: float,
    venue: str,
) -> None:
    """
    使用事件驱动引擎运行回测

    使用事件驱动的专业回测框架，支持更复杂的策略和更精确的执行模拟
    支持多品种回测
    """
    # 延迟导入
    from backtest.cli_core import (
        CLICore, get_system_config, get_symbols_from_data_pool,
        DataPreparationError, DownloadFailureType
    )
    from backtest.result_analysis import output_results
    from utils.validation import parse_symbols, parse_timeframes

    # 延迟导入事件驱动引擎相关模块，避免在不需要时加载
    try:
        from decimal import Decimal
        from backtest.engines.event_engine import EventDrivenBacktestEngine
        from nautilus_trader.model import Venue
        from nautilus_trader.model.enums import AccountType, OmsType
        from nautilus_trader.model.objects import Money
        from nautilus_trader.model.data import BarType
        from nautilus_trader.test_kit.providers import TestInstrumentProvider
        from nautilus_trader.persistence.wranglers import BarDataWrangler
        import pandas as pd
    except ImportError as e:
        print(f"错误：无法导入事件驱动引擎模块: {e}")
        print("请确保已安装必要的依赖")
        raise typer.Exit(1)

    # 创建CLI核心（用于数据准备）
    cli_core = CLICore(verbose=verbose, detail=detail)

    # 从系统配置读取默认值
    system_config = get_system_config()
    default_trading_mode = system_config['default_trading_mode']
    default_timeframes = system_config['default_timeframes']

    # 使用命令行参数或默认值
    trading_mode = trading_mode or default_trading_mode
    timeframes = timeframes or ','.join(default_timeframes) if isinstance(default_timeframes, list) else default_timeframes

    # 解析货币对列表
    symbols_list = []
    if pool:
        print(f"从自选组合 '{pool}' 获取货币对...")
        try:
            symbols_list = get_symbols_from_data_pool(pool)
            if not symbols_list:
                print(f"错误：自选组合 '{pool}' 中没有货币对")
                raise typer.Exit(1)
            print(f"成功获取 {len(symbols_list)} 个货币对: {', '.join(symbols_list)}")
        except ValueError as e:
            print(f"错误：{e}")
            raise typer.Exit(1)
    elif symbols:
        symbols_list = parse_symbols(symbols)
    else:
        symbols_list = ['BTCUSDT']

    # 解析时间周期列表
    timeframes_list = parse_timeframes(timeframes)

    # 生成输出文件名
    if output is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = str(cli_core.results_dir / f"{strategy_name}_{timestamp}_event_results.{output_format}")
    else:
        output_file = output

    # 准备数据
    if data_path:
        # 从文件加载数据（单品种模式）
        print(f"从文件加载数据: {data_path}")
        try:
            df = pd.read_csv(data_path, index_col=0, parse_dates=True)
            required_columns = ['Open', 'High', 'Low', 'Close', 'Volume']
            for col in required_columns:
                if col not in df.columns:
                    print(f"数据文件缺少必要列: {col}")
                    raise typer.Exit(1)
            data_dict = {f"{symbols_list[0]}_{timeframes_list[0]}": df}
        except Exception as e:
            print(f"加载数据文件失败: {e}")
            raise typer.Exit(1)
    else:
        # 从数据库加载数据
        print("从数据库加载数据...")
        try:
            data_dict, download_results = cli_core.prepare_data(
                symbols=symbols_list,
                timeframes=timeframes_list,
                time_range=time_range,
                trading_mode=trading_mode or 'spot',
                auto_download=auto_download,
                ignore_missing=ignore_missing,
                show_progress=not no_progress
            )

            if not data_dict:
                print("\n✗ 没有成功加载任何数据，回测无法继续")
                raise typer.Exit(1)

            print(f"\n✓ 成功加载 {len(data_dict)} 个品种的数据")

        except DataPreparationError as e:
            print(f"错误：{e}")
            raise typer.Exit(1)

    print(f"\n货币对: {', '.join(symbols_list)}")
    print(f"时间周期: {', '.join(timeframes_list)}")
    print(f"交易模式: {trading_mode}")
    print(f"初始资金: {init_cash} {base_currency}")
    print(f"手续费率: {fees}")
    print(f"杠杆倍数: {leverage}")
    if time_range:
        print(f"时间范围: {time_range}")
    print()

    # 初始化事件驱动引擎
    try:
        print("初始化事件驱动回测引擎...")

        # 解析时间范围
        if time_range:
            from utils.validation import parse_time_range
            start_dt, end_dt = parse_time_range(time_range)
            start_date = start_dt.strftime('%Y-%m-%d') if start_dt else '2023-01-01'
            end_date = end_dt.strftime('%Y-%m-%d') if end_dt else '2023-12-31'
        else:
            # 默认使用第一个数据的时间范围
            first_key = list(data_dict.keys())[0]
            first_df = data_dict[first_key]
            if len(first_df) > 0:
                first_idx = first_df.index[0]
                last_idx = first_df.index[-1]
                # 处理可能是Timestamp或datetime的情况
                start_date = str(first_idx)[:10] if first_idx is not None else '2023-01-01'
                end_date = str(last_idx)[:10] if last_idx is not None else '2023-12-31'
            else:
                start_date = '2023-01-01'
                end_date = '2023-12-31'

        # 创建引擎配置
        engine_config = {
            "trader_id": f"BACKTEST-{strategy_name.upper()}",
            "log_level": "DEBUG" if verbose else "INFO",
            "initial_capital": init_cash,
            "start_date": start_date,
            "end_date": end_date,
        }

        # 创建引擎实例
        engine = EventDrivenBacktestEngine(engine_config)
        engine.initialize()

        # 为每个品种创建交易品种并加载数据
        instruments = {}
        bar_types = {}
        all_bars = []

        # 使用第一个品种的venue作为交易所
        first_symbol = symbols_list[0]
        first_timeframe = timeframes_list[0]
        first_key = f"{first_symbol}_{first_timeframe}"

        # 创建第一个品种以获取venue
        print(f"创建交易品种: {first_symbol}")
        try:
            if first_symbol == 'BTCUSDT' or first_symbol == 'BTC/USDT':
                first_instrument = TestInstrumentProvider.btcusdt_binance()
            elif first_symbol == 'ETHUSDT' or first_symbol == 'ETH/USDT':
                first_instrument = TestInstrumentProvider.ethusdt_binance()
            else:
                first_instrument = TestInstrumentProvider.btcusdt_binance()
            instrument_venue = str(first_instrument.id.venue)
            print(f"交易品种所属交易所: {instrument_venue}")
        except Exception as e:
            print(f"创建交易品种失败: {e}")
            first_instrument = TestInstrumentProvider.btcusdt_binance()
            instrument_venue = "BINANCE"

        # 添加交易所（使用品种对应的venue）
        print(f"添加交易所: {instrument_venue}")
        from decimal import Decimal
        engine.add_venue(
            venue_name=instrument_venue,
            oms_type=OmsType.NETTING,
            account_type=AccountType.MARGIN,
            starting_capital=init_cash,
            base_currency=base_currency,
            default_leverage=Decimal(str(leverage)),
        )

        # 为每个品种创建instrument并加载数据
        for symbol in symbols_list:
            # 使用第一个时间周期（多时间周期支持需要更复杂的策略配置）
            timeframe = timeframes_list[0]
            key = f"{symbol}_{timeframe}"

            if key not in data_dict:
                print(f"警告：跳过 {key}，数据未加载")
                continue

            df = data_dict[key]

            # 创建交易品种
            print(f"创建交易品种: {symbol}")
            try:
                if symbol == 'BTCUSDT' or symbol == 'BTC/USDT':
                    instrument = TestInstrumentProvider.btcusdt_binance()
                elif symbol == 'ETHUSDT' or symbol == 'ETH/USDT':
                    instrument = TestInstrumentProvider.ethusdt_binance()
                else:
                    # 对于其他品种，使用默认的BTC/USDT作为模板
                    instrument = TestInstrumentProvider.btcusdt_binance()
            except Exception as e:
                print(f"创建交易品种失败: {e}，使用默认品种")
                instrument = TestInstrumentProvider.btcusdt_binance()

            engine.add_instrument(instrument)
            instruments[symbol] = instrument

            # 转换数据格式并加载
            print(f"转换并加载 {symbol} 数据...")

            # 标准化DataFrame列名
            df = df.copy()
            df.columns = [col.lower() for col in df.columns]

            # 确保索引是带时区的datetime类型
            if not isinstance(df.index, pd.DatetimeIndex):
                if 'timestamp' in df.columns:
                    df = df.set_index('timestamp')
                df.index = pd.to_datetime(df.index, utc=True)

            # 确保所有价格列都是float64类型
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in df.columns:
                    df[col] = df[col].astype('float64')

            # 创建BarType
            bar_type_str = f"{instrument.id}-{_convert_timeframe_to_event(timeframe)}-LAST-EXTERNAL"
            bar_type = BarType.from_str(bar_type_str)
            bar_types[symbol] = bar_type

            # 使用BarDataWrangler转换数据
            wrangler = BarDataWrangler(bar_type, instrument)
            bars = wrangler.process(df)

            # 添加数据到引擎（通过引擎的公共方法）
            if hasattr(engine, 'engine') and engine.engine is not None:
                engine.engine.add_data(bars)
            engine._data.extend(bars)
            all_bars.extend(bars)
            print(f"✓ 成功加载 {symbol} 的 {len(bars)} 条K线数据")

        print(f"\n共加载 {len(instruments)} 个品种，{len(all_bars)} 条K线数据")

        # 加载策略（传入所有品种的bar_types和instruments）
        print(f"加载事件驱动策略: {strategy_name}")
        strategy = _load_event_strategy_multi(
            strategy_name, strategy_params, bar_types, instruments
        )

        if strategy is None:
            print(f"错误：无法加载策略 {strategy_name}")
            print("请确保策略继承自EventDrivenStrategy或使用兼容的策略基类")
            raise typer.Exit(1)

        engine.add_strategy(strategy)

        # 执行回测
        print("\n开始执行回测...")
        results = engine.run_backtest()

        # 处理结果
        print("\n处理回测结果...")
        formatted_results = _format_event_results_multi(
            results, symbols_list, timeframes_list[0], strategy_name, instruments
        )

        # 输出结果
        output_results(formatted_results, output_format, output_file)

        # 保存到数据库
        if save_to_db:
            print("\n正在保存结果到数据库...")
            config = {
                'init_cash': init_cash,
                'fees': fees,
                'slippage': slippage,
                'trading_mode': trading_mode,
                'time_range': time_range,
                'strategy_params': strategy_params,
                'engine': 'event',
                'base_currency': base_currency,
                'leverage': leverage,
                'venue': venue,
            }
            if cli_core.save_to_database(formatted_results, strategy_name, config):
                print("✓ 结果已成功保存到数据库")
            else:
                print("✗ 保存到数据库失败")

        # 打印回测摘要（在清理资源之前，避免日志打断输出）
        print("\n" + "=" * 70)
        print("事件驱动回测成功完成！")
        print("=" * 70)

        # 打印组合级别摘要
        portfolio = formatted_results.get('portfolio', {})
        portfolio_metrics = portfolio.get('metrics', {})
        print(f"\n投资组合回测结果摘要:")
        print(f"  品种数量: {len(symbols_list)}")
        print(f"  总收益率: {portfolio_metrics.get('total_return', 0):.2f}%")
        print(f"  总交易次数: {portfolio_metrics.get('total_trades', 0)}")
        print(f"  胜率: {portfolio_metrics.get('win_rate', 0):.2f}%")
        print(f"  盈亏比: {portfolio_metrics.get('profit_factor', 0):.2f}")
        print(f"  夏普比率: {portfolio_metrics.get('sharpe_ratio', 0):.4f}")
        print(f"  最大回撤: {portfolio_metrics.get('max_drawdown', 0):.2f}%")
        print(f"  总盈亏: {portfolio_metrics.get('total_pnl', 0):.2f}")
        print("=" * 70)

        # 清理引擎资源（放在最后，避免日志打断结论输出）
        engine.cleanup()

    except Exception as e:
        print(f"错误：事件驱动回测执行失败: {e}")
        import traceback
        traceback.print_exc()
        raise typer.Exit(1)


def _load_event_strategy(strategy_name: str, strategy_params: dict, bar_type, instrument_id):
    """
    加载事件驱动策略

    尝试从backend/strategies目录加载策略类

    参数：
        strategy_name: 策略名称（文件名，不含.py后缀）
        strategy_params: 策略参数字典
        bar_type: BarType对象，用于策略初始化
        instrument_id: 交易品种ID，用于策略配置

    返回：
        Strategy实例或None（如果加载失败）
    """
    try:
        import importlib
        from pathlib import Path
        
        # 添加策略目录到路径
        backend_path = Path(__file__).resolve().parent.parent
        strategies_dir = backend_path / 'strategies'
        if str(strategies_dir) not in sys.path:
            sys.path.insert(0, str(strategies_dir))
        
        # 清除模块缓存
        if strategy_name in sys.modules:
            del sys.modules[strategy_name]
        
        # 检查策略文件
        strategy_file = strategies_dir / f"{strategy_name}.py"
        if not strategy_file.exists():
            print(f"策略文件不存在: {strategy_file}")
            return None
        
        # 导入策略模块
        module = importlib.import_module(strategy_name)
        
        # 查找策略类和配置类
        strategy_class = None
        config_class = None
        
        # 尝试查找事件驱动策略
        # 首先尝试导入Strategy基类（从新的strategy模块）
        try:
            from backtest.strategies.strategy import Strategy, StrategyConfig
            EventDrivenStrategy = Strategy
            EventDrivenStrategyConfig = StrategyConfig
        except ImportError:
            # 如果无法导入，尝试其他路径
            try:
                from backend.backtest.strategies.strategy import Strategy, StrategyConfig
                EventDrivenStrategy = Strategy
                EventDrivenStrategyConfig = StrategyConfig
            except ImportError:
                # 最后尝试从nautilus_trader导入
                from nautilus_trader.trading.strategy import Strategy
                EventDrivenStrategy = Strategy
                EventDrivenStrategyConfig = None
        
        for name in dir(module):
            obj = getattr(module, name)
            if isinstance(obj, type):
                # 查找策略类（继承自EventDrivenStrategy或Strategy）
                if issubclass(obj, EventDrivenStrategy) and obj != EventDrivenStrategy:
                    strategy_class = obj
                    print(f"找到策略类: {name}")
                # 查找配置类
                elif EventDrivenStrategyConfig and issubclass(obj, EventDrivenStrategyConfig) and obj != EventDrivenStrategyConfig:
                    config_class = obj
                    print(f"找到配置类: {name}")
        
        if strategy_class is None:
            print(f"在模块 {strategy_name} 中找不到事件驱动策略类")
            return None
        
        # 创建策略实例
        if config_class:
            # 使用配置类创建策略 - 新参数结构：统一使用列表
            config_params = strategy_params.copy()
            config_params['instrument_ids'] = [instrument_id]
            config_params['bar_types'] = [bar_type]
            config = config_class(**config_params)
            strategy = strategy_class(config)
        else:
            # 直接使用参数创建策略
            strategy_params['instrument_ids'] = [instrument_id]
            strategy_params['bar_types'] = [bar_type]
            strategy = strategy_class(**strategy_params)

        print(f"成功加载事件驱动策略: {strategy_class.__name__}")
        return strategy

    except Exception as e:
        print(f"加载事件驱动策略失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def _convert_timeframe_to_event(timeframe: str) -> str:
    """
    将时间周期转换为事件驱动引擎格式
    
    参数：
        timeframe: 时间周期字符串（如 1h, 15m, 1d）
        
    返回：
        str: 事件驱动引擎格式的时间周期（如 1-HOUR, 15-MINUTE, 1-DAY）
    """
    # 映射表
    mapping = {
        '1m': '1-MINUTE',
        '3m': '3-MINUTE',
        '5m': '5-MINUTE',
        '15m': '15-MINUTE',
        '30m': '30-MINUTE',
        '1h': '1-HOUR',
        '2h': '2-HOUR',
        '4h': '4-HOUR',
        '6h': '6-HOUR',
        '8h': '8-HOUR',
        '12h': '12-HOUR',
        '1d': '1-DAY',
        '3d': '3-DAY',
        '1w': '1-WEEK',
        '1M': '1-MONTH',
    }
    
    return mapping.get(timeframe, '1-HOUR')


def _format_event_results(results: dict, symbol: str, timeframe: str, strategy_name: str) -> dict:
    """
    格式化事件驱动回测结果为QuantCell标准格式（单品种版本，保持向后兼容）

    参数：
        results: 事件驱动回测结果
        symbol: 货币对
        timeframe: 时间周期
        strategy_name: 策略名称

    返回：
        dict: 格式化的回测结果
    """
    key = f"{symbol}_{timeframe}"

    formatted = {
        key: {
            'symbol': symbol,
            'timeframe': timeframe,
            'metrics': results.get('metrics', {}),
            'trades': results.get('trades', []),
            'positions': results.get('positions', []),
            'equity_curve': results.get('equity_curve', []),
        }
    }

    # 添加全局账户信息（跨所有交易对）
    formatted['account'] = results.get('account', {})

    # 添加投资组合汇总（单品种时与品种结果相同）
    formatted['portfolio'] = {
        'metrics': results.get('metrics', {}),
        'trades': results.get('trades', []),
        'equity_curve': results.get('equity_curve', []),
    }

    # 添加元数据
    now = datetime.now()
    formatted['_meta'] = {
        'engine': 'event',
        'strategy': strategy_name,
        'timestamp': int(now.timestamp()),  # Unix时间戳（秒，数值型）
        'formatted_time': now.strftime('%Y-%m-%d %H:%M:%S'),  # 格式化时间字符串
    }

    return formatted


def _load_event_strategy_multi(
    strategy_name: str,
    strategy_params: dict,
    bar_types: dict,
    instruments: dict
):
    """
    加载支持多品种的事件驱动策略

    支持两种策略类型：
    1. 策略接口（StrategyBase）：使用 StrategyAdapter 包装
    2. 传统策略接口（Strategy/StrategyAdapter）：直接使用

    参数：
        strategy_name: 策略名称（文件名，不含.py后缀）
        strategy_params: 策略参数字典
        bar_types: 品种到BarType的映射字典
        instruments: 品种到instrument的映射字典

    返回：
        Strategy实例或None（如果加载失败）
    """
    try:
        import importlib
        from pathlib import Path

        # 添加策略目录到路径
        backend_path = Path(__file__).resolve().parent.parent
        strategies_dir = backend_path / 'strategies'
        if str(strategies_dir) not in sys.path:
            sys.path.insert(0, str(strategies_dir))

        # 清除模块缓存
        if strategy_name in sys.modules:
            del sys.modules[strategy_name]

        # 检查策略文件
        strategy_file = strategies_dir / f"{strategy_name}.py"
        if not strategy_file.exists():
            print(f"策略文件不存在: {strategy_file}")
            return None

        # 导入策略模块
        module = importlib.import_module(strategy_name)

        # 查找策略类和配置类
        strategy_class = None
        config_class = None
        is_core_strategy = False

        # 导入策略基类
        try:
            # 尝试导入策略接口
            from strategy.core import StrategyBase as CoreStrategyBase, StrategyConfig as CoreStrategyConfig
            StrategyBase = CoreStrategyBase
            StrategyConfig = CoreStrategyConfig
        except ImportError as e:
            print(f"导入 strategy.core 失败: {e}")
            StrategyBase = None
            StrategyConfig = None

        try:
            # 尝试导入回测适配器
            from backtest.strategies.strategy_adapter import StrategyAdapter, StrategyConfig as AdapterStrategyConfig
            EventDrivenStrategy = StrategyAdapter
            EventDrivenStrategyConfig = AdapterStrategyConfig
        except ImportError as e:
            try:
                from backend.backtest.strategies.strategy_adapter import StrategyAdapter, StrategyConfig as AdapterStrategyConfig
                EventDrivenStrategy = StrategyAdapter
                EventDrivenStrategyConfig = AdapterStrategyConfig
            except ImportError as e:
                print(f"导入 backtest.strategies.strategy_adapter 失败: {e}")
                # 最后尝试从nautilus_trader导入
                from nautilus_trader.trading.strategy import Strategy
                EventDrivenStrategy = Strategy
                EventDrivenStrategyConfig = None

        for name in dir(module):
            obj = getattr(module, name)
            if isinstance(obj, type):
                # 首先检查是否是策略接口（StrategyBase）
                if StrategyBase and issubclass(obj, StrategyBase) and obj != StrategyBase:
                    strategy_class = obj
                    is_core_strategy = True
                    print(f"找到策略类: {name}")
                # 然后检查是否是传统策略类
                elif issubclass(obj, EventDrivenStrategy) and obj != EventDrivenStrategy:
                    strategy_class = obj
                    is_core_strategy = False
                    print(f"找到策略类: {name}")

                # 查找配置类（优先配置类）
                if StrategyConfig and issubclass(obj, StrategyConfig) and obj != StrategyConfig:
                    config_class = obj
                    print(f"找到配置类: {name}")
                elif EventDrivenStrategyConfig and issubclass(obj, EventDrivenStrategyConfig) and obj != EventDrivenStrategyConfig:
                    config_class = obj
                    print(f"找到配置类: {name}")

        if strategy_class is None:
            print(f"在模块 {strategy_name} 中找不到策略类")
            return None

        # 准备品种ID列表和K线类型列表（统一使用列表形式）
        # 将 NautilusTrader InstrumentId 转换为InstrumentId
        from strategy.core import InstrumentId as InstrumentId
        instrument_ids_list = []
        for inst in instruments.values():
            # 从 NautilusTrader InstrumentId 提取 symbol 和 venue
            symbol = str(inst.id.symbol)
            venue = str(inst.id.venue)
            unified_id = InstrumentId(symbol=symbol, venue=venue)
            instrument_ids_list.append(unified_id)
        bar_types_list = list(bar_types.values())

        # 创建策略实例
        if config_class:
            # 使用配置类创建策略
            config_params = strategy_params.copy()
            config_params['instrument_ids'] = instrument_ids_list
            config_params['bar_types'] = bar_types_list
            config = config_class(**config_params)
            user_strategy = strategy_class(config)
        else:
            # 直接使用参数创建策略
            strategy_params_copy = strategy_params.copy()
            strategy_params_copy['instrument_ids'] = instrument_ids_list
            strategy_params_copy['bar_types'] = bar_types_list
            user_strategy = strategy_class(**strategy_params_copy)

        # 如果是策略接口，需要使用 StrategyAdapter 包装
        if is_core_strategy:
            print(f"检测到策略接口，创建回测适配策略")
            from backtest.strategies.strategy_adapter import StrategyAdapter, StrategyConfig as AdapterStrategyConfig

            # 创建适配器配置（从统一配置转换）
            if isinstance(user_strategy.config, AdapterStrategyConfig):
                adapter_config = user_strategy.config
            else:
                adapter_config = AdapterStrategyConfig(
                    instrument_ids=user_strategy.config.instrument_ids,
                    bar_types=user_strategy.config.bar_types,
                    trade_size=user_strategy.config.trade_size,
                    log_level=user_strategy.config.log_level,
                )

            # 创建动态类，继承 StrategyAdapter 和用户策略类
            # 这样新类既有 StrategyAdapter 的交易接口实现，又有用户策略的 on_bar 逻辑
            user_strategy_class = user_strategy.__class__

            # 定义动态类
            class BacktestStrategyAdapter(StrategyAdapter, user_strategy_class):
                """回测用的策略适配器，同时继承 StrategyAdapter 和用户策略类"""

                def __init__(self, adapter_config, user_strategy_instance):
                    # 调用 StrategyAdapter 的 __init__（使用 adapter_config）
                    StrategyAdapter.__init__(self, adapter_config)
                    # 使用用户策略实例的原始配置（包含 fast_period, slow_period 等）
                    self._config = user_strategy_instance._config
                    # 使用不同的属性名避免与 NautilusTrader 冲突
                    self._strategy_is_running = False
                    self.bars_processed = 0
                    self.start_time = None
                    self.end_time = None
                    # 初始化用户策略特有的状态
                    self._init_user_strategy_state(self._config)
                    # 保存用户策略实例
                    self._user_strategy_instance = user_strategy_instance

                def _init_user_strategy_state(self, config):
                    """初始化用户策略的状态"""
                    # 为每个品种维护独立的数据结构
                    self.prices = {}
                    self.fast_sma = {}
                    self.slow_sma = {}
                    self.prev_fast_sma = {}
                    self.prev_slow_sma = {}
                    # 初始化每个品种的数据结构
                    for instrument_id in config.instrument_ids:
                        self.prices[instrument_id] = []
                        self.fast_sma[instrument_id] = 0.0
                        self.slow_sma[instrument_id] = 0.0
                        self.prev_fast_sma[instrument_id] = 0.0
                        self.prev_slow_sma[instrument_id] = 0.0

                def on_start(self) -> None:
                    """策略启动"""
                    StrategyAdapter.on_start(self)
                    # 调用用户策略的 on_start
                    user_strategy_class.on_start(self)

                def on_bar(self, bar) -> None:
                    """K线数据处理"""
                    # 使用 StrategyAdapter 的转换方法
                    self.bars_processed += 1
                    unified_bar = self._to_unified_bar(bar)
                    # 调用用户策略的 on_bar
                    user_strategy_class.on_bar(self, unified_bar)

                def on_stop(self) -> None:
                    """策略停止"""
                    # 调用用户策略的 on_stop
                    user_strategy_class.on_stop(self)
                    # 调用 StrategyAdapter 的 on_stop
                    StrategyAdapter.on_stop(self)

            # 创建适配策略实例
            strategy = BacktestStrategyAdapter(adapter_config, user_strategy)

            print(f"成功加载策略: {strategy_class.__name__}（支持 {len(instruments)} 个品种）")
        else:
            strategy = user_strategy
            print(f"成功加载事件驱动策略: {strategy_class.__name__}（支持 {len(instruments)} 个品种）")

        return strategy

    except Exception as e:
        print(f"加载事件驱动策略失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def _format_event_results_multi(
    results: dict,
    symbols_list: list,
    timeframe: str,
    strategy_name: str,
    instruments: dict
) -> dict:
    """
    格式化多品种事件驱动回测结果为QuantCell标准格式

    参数：
        results: 事件驱动回测结果
        symbols_list: 货币对列表
        timeframe: 时间周期
        strategy_name: 策略名称
        instruments: 品种到instrument的映射字典

    返回：
        dict: 格式化的回测结果，包含symbols和portfolio键
    """
    from datetime import datetime
    import numpy as np

    formatted = {
        'symbols': {},
        'portfolio': {},
        'account': results.get('account', {}),
        '_meta': {
            'engine': 'event',
            'strategy': strategy_name,
            'timestamp': int(datetime.now().timestamp()),
            'formatted_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'symbol_count': len(symbols_list),
            'symbols': symbols_list,
            'timeframe': timeframe,
        }
    }

    # 获取所有交易和持仓
    all_trades = results.get('trades', [])
    all_positions = results.get('positions', [])
    equity_curve = results.get('equity_curve', [])

    # 按品种分组交易和持仓
    symbol_trades = {symbol: [] for symbol in symbols_list}
    symbol_positions = {symbol: [] for symbol in symbols_list}

    # 将交易分配到各品种
    for trade in all_trades:
        instrument_id = trade.get('instrument_id', '')
        # 从instrument_id中提取品种代码
        for symbol in symbols_list:
            if symbol.replace('/', '') in instrument_id or symbol in instrument_id:
                symbol_trades[symbol].append(trade)
                break

    # 将持仓分配到各品种
    for position in all_positions:
        instrument_id = position.get('instrument_id', '')
        for symbol in symbols_list:
            if symbol.replace('/', '') in instrument_id or symbol in instrument_id:
                symbol_positions[symbol].append(position)
                break

    # 为每个品种创建结果
    for symbol in symbols_list:
        key = f"{symbol}_{timeframe}"
        trades = symbol_trades.get(symbol, [])
        positions = symbol_positions.get(symbol, [])

        # 计算该品种的指标
        symbol_metrics = _calculate_symbol_metrics(trades, positions, results.get('account', {}))

        formatted['symbols'][key] = {
            'symbol': symbol,
            'timeframe': timeframe,
            'metrics': symbol_metrics,
            'trades': trades,
            'positions': positions,
            # 注意：equity_curve 只在 portfolio 级别保留，避免数据冗余
        }

    # 计算组合级别指标
    portfolio_metrics = _calculate_portfolio_metrics(
        all_trades, all_positions, equity_curve, symbols_list, results.get('account', {})
    )

    formatted['portfolio'] = {
        'metrics': portfolio_metrics,
        'trades': all_trades,
        'positions': all_positions,
        'equity_curve': equity_curve,
        'correlations': portfolio_metrics.get('correlations', {}),
    }

    return formatted


def _calculate_symbol_metrics(trades: list, positions: list, account: dict) -> dict:
    """
    计算单个品种的绩效指标

    参数：
        trades: 该品种的交易列表
        positions: 该品种的持仓列表
        account: 账户信息

    返回：
        dict: 品种绩效指标
    """
    if not trades:
        return {
            'total_return': 0.0,
            'sharpe_ratio': 0.0,
            'max_drawdown': 0.0,
            'win_rate': 0.0,
            'profit_factor': 0.0,
            'total_trades': 0,
            'total_pnl': 0.0,
        }

    import re

    # 从持仓数据中提取盈亏（更准确）
    pnls = []
    for position in positions:
        pnl_str = position.get('realized_pnl', '0')
        if isinstance(pnl_str, str):
            # 提取数值部分，如 "-78.00573100 USDT" -> -78.00573100
            match = re.match(r'^([+-]?\d+\.?\d*)', pnl_str.strip())
            if match:
                try:
                    pnl = float(match.group(1))
                    pnls.append(pnl)
                except ValueError:
                    pass
        elif isinstance(pnl_str, (int, float)):
            pnls.append(float(pnl_str))

    # 如果没有从持仓提取到盈亏，尝试从交易数据计算（备用方案）
    if not pnls and trades:
        # 这里可以实现基于交易价格计算盈亏的逻辑
        # 目前先返回0，因为持仓数据更可靠
        pass

    winning_trades = [p for p in pnls if p > 0]
    losing_trades = [p for p in pnls if p < 0]

    total_pnl = sum(pnls)
    win_rate = len(winning_trades) / len(pnls) * 100 if pnls else 0

    profit_factor = 0.0
    if losing_trades:
        gross_profit = sum(winning_trades) if winning_trades else 0
        gross_loss = abs(sum(losing_trades))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0.0

    # 计算总收益率
    initial_balance = account.get('initial_balance', 100000.0)
    total_return = (total_pnl / initial_balance) * 100 if initial_balance > 0 else 0.0

    return {
        'total_return': round(total_return, 2),
        'win_rate': round(win_rate, 2),
        'profit_factor': round(profit_factor, 2),
        'total_trades': len(trades),
        'winning_trades': len(winning_trades),
        'losing_trades': len(losing_trades),
        'total_pnl': round(total_pnl, 2),
        'sharpe_ratio': 0.0,  # 需要权益曲线数据计算
        'max_drawdown': 0.0,  # 需要权益曲线数据计算
    }


def _calculate_portfolio_metrics(
    all_trades: list,
    all_positions: list,
    equity_curve: list,
    symbols_list: list,
    account: dict
) -> dict:
    """
    计算组合级别的绩效指标

    参数：
        all_trades: 所有交易
        all_positions: 所有持仓
        equity_curve: 权益曲线
        symbols_list: 品种列表
        account: 账户信息

    返回：
        dict: 组合绩效指标
    """
    import numpy as np

    # 基础统计
    total_trades = len(all_trades)

    # 从权益曲线计算收益率和回撤
    total_return = 0.0
    sharpe_ratio = 0.0
    max_drawdown = 0.0

    if equity_curve and len(equity_curve) > 1:
        equities = [point.get('equity', 0) for point in equity_curve]

        if len(equities) > 1 and equities[0] > 0:
            # 计算总收益率
            total_return = ((equities[-1] - equities[0]) / equities[0]) * 100

            # 计算收益率序列
            returns = []
            for i in range(1, len(equities)):
                if equities[i-1] > 0:
                    ret = (equities[i] - equities[i-1]) / equities[i-1]
                    returns.append(ret)

            # 计算夏普比率
            if len(returns) > 1:
                avg_return = np.mean(returns)
                std_return = np.std(returns, ddof=1)
                # 假设无风险利率为0，年化因子假设每小时数据，每年252个交易日，每天24小时
                periods_per_year = 252 * 24
                if std_return > 0:
                    sharpe_ratio = (avg_return / std_return) * np.sqrt(periods_per_year)

            # 计算最大回撤
            peak = equities[0]
            for equity in equities:
                if equity > peak:
                    peak = equity
                drawdown = (peak - equity) / peak if peak > 0 else 0
                if drawdown > max_drawdown:
                    max_drawdown = drawdown
            max_drawdown = max_drawdown * 100  # 转换为百分比

    # 计算总盈亏
    total_pnl = account.get('final_balance', 0) - account.get('initial_balance', account.get('balance', 0))

    # 计算胜率
    # 从持仓数据计算盈亏
    pnls = []
    for position in all_positions:
        pnl_str = position.get('realized_pnl', '0')
        if isinstance(pnl_str, str):
            import re
            match = re.match(r'^([+-]?\d+\.?\d*)', pnl_str.strip())
            if match:
                try:
                    pnl = float(match.group(1))
                    if pnl != 0:
                        pnls.append(pnl)
                except ValueError:
                    pass
        elif isinstance(pnl_str, (int, float)):
            pnls.append(float(pnl_str))

    winning_trades = len([p for p in pnls if p > 0])
    win_rate = (winning_trades / len(pnls) * 100) if pnls else 0.0

    # 计算盈亏比
    profit_factor = 0.0
    if pnls:
        gross_profit = sum([p for p in pnls if p > 0])
        gross_loss = abs(sum([p for p in pnls if p < 0]))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0.0

    # 计算品种间相关性（简化版本）
    correlations = {}
    if len(symbols_list) > 1:
        # 这里可以添加更复杂的相关性计算
        # 目前返回空字典，表示相关性数据需要更详细的实现
        correlations = {symbol: {} for symbol in symbols_list}

    return {
        'total_return': round(total_return, 2),
        'sharpe_ratio': round(sharpe_ratio, 2),
        'max_drawdown': round(max_drawdown, 2),
        'win_rate': round(win_rate, 2),
        'profit_factor': round(profit_factor, 2),
        'total_trades': total_trades,
        'winning_trades': winning_trades,
        'losing_trades': len(pnls) - winning_trades if pnls else 0,
        'total_pnl': round(total_pnl, 2),
        'initial_equity': account.get('initial_balance', account.get('balance', 0)),
        'final_equity': account.get('final_balance', account.get('equity', 0)),
        'correlations': correlations,
    }


@app.command()
def plot(
    input_file: Annotated[str, typer.Argument(help="JSON格式的回测结果文件名或路径")],
    output: Annotated[Optional[str], typer.Option("--output", "-o", help="输出图片文件路径")] = None,
    show: Annotated[bool, typer.Option("--show/--no-show", help="是否显示图表")] = False,
    plot_type: Annotated[str, typer.Option("--plot-type", "-t", help="图表类型：all/equity/trades/metrics")] = "all",
    merged: Annotated[bool, typer.Option("--merged/--no-merged", "-m/-nm", help="是否生成合并报告（多交易对时默认启用）")] = True,
    separate: Annotated[bool, typer.Option("--separate/--no-separate", "-s/-ns", help="是否同时生成各交易对单独图表")] = False
):
    """
    加载回测结果并绘制可视化图表

    默认自动合并多交易对结果生成综合报告。使用 --separate 可同时生成各交易对单独图表。

    示例:
      # 使用文件名（自动在默认结果目录中查找）
      python backtest_cli.py plot sma_cross_strategy_20260207_195120_results.json

      # 使用相对路径
      python backtest_cli.py plot results/my_results.json

      # 使用绝对路径
      python backtest_cli.py plot /path/to/results.json
    """
    # 延迟导入
    from backtest.result_analysis import load_results
    from backtest.plot_utils import plot_results
    from backtest.merged_report import generate_merged_report

    print("=" * 70)
    print("加载回测结果并绘制图表")
    print("=" * 70)
    print()

    # 处理文件路径
    input_path = Path(input_file)

    # 如果文件不存在且不是绝对路径，尝试在默认结果目录中查找
    if not input_path.exists() and not input_path.is_absolute():
        # 获取默认结果目录
        default_results_dir = Path(__file__).parent / 'results'
        full_path = default_results_dir / input_file
        if full_path.exists():
            input_path = full_path
            print(f"✓ 在默认目录找到文件: {input_path}")

    # 验证文件是否存在
    if not input_path.exists():
        print(f"错误：文件不存在: {input_file}")
        print(f"  查找路径: {input_path}")
        if not input_path.is_absolute():
            default_results_dir = Path(__file__).parent / 'results'
            print(f"  默认结果目录: {default_results_dir}")
        raise typer.Exit(1)

    if not str(input_path).lower().endswith('.json'):
        print("错误：仅支持JSON格式文件")
        raise typer.Exit(1)

    # 使用解析后的路径加载结果
    input_file = str(input_path)
    results = load_results(input_file)
    if results is None:
        print("错误：加载结果失败")
        raise typer.Exit(1)
    
    # 过滤掉内部键（以下划线开头）
    symbol_results = {k: v for k, v in results.items() if not k.startswith('_')}
    symbol_count = len(symbol_results)
    
    print(f"✓ 成功加载回测结果文件: {input_file}")
    print(f"  包含 {symbol_count} 个交易对的数据")
    print()
    
    # 确定输出目录
    output_dir = str(input_path.parent) if output is None else str(Path(output).parent)
    
    try:
        # 1. 生成合并报告（多交易对时默认启用）
        if merged and symbol_count > 1:
            print("-" * 70)
            print("生成合并报告（多交易对综合视图）")
            print("-" * 70)
            merged_report_path = generate_merged_report(input_file, output_dir=output_dir, show=show)
            print()
        
        # 2. 生成各交易对单独图表（如果需要）
        if separate or (not merged and symbol_count > 0):
            print("-" * 70)
            print("生成各交易对单独图表")
            print("-" * 70)
            
            if output is None:
                separate_output = str(input_path.with_suffix('.png'))
            else:
                separate_output = output
            
            plot_results(results, separate_output, show, plot_type)
            print()
        
        print("=" * 70)
        print("图表生成完成！")
        print("=" * 70)
        
        # 输出生成的文件列表
        if merged and symbol_count > 1:
            print(f"\n生成的报告文件:")
            print(f"  • 合并报告: {merged_report_path}")
            if separate:
                print(f"  • 单独图表: {separate_output}")
        
    except Exception as e:
        print(f"错误：绘制图表失败: {e}")
        import traceback
        traceback.print_exc()
        raise typer.Exit(1)


if __name__ == '__main__':
    app()
