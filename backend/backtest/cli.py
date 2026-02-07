# -*- coding: utf-8 -*-
"""
回测CLI命令入口

提供Typer命令定义，调用cli_core模块实现具体功能
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from typing_extensions import Annotated

from backtest.cli_core import (
    CLICore, get_system_config, get_symbols_from_data_pool,
    DataPreparationError, StrategyLoadError, BacktestExecutionError,
    DownloadFailureType
)
from backtest.result_analysis import output_results, load_results
from utils.validation import (
    validate_time_range, validate_symbols, validate_timeframes, 
    validate_trading_mode, parse_symbols, parse_timeframes
)
from utils.logger import setup_logger, get_default_log_file

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
    """
)


@app.command()
def run(
    strategy: Annotated[str, typer.Option("--strategy", "-s", help="策略文件名（不带.py后缀）")],
    params: Annotated[str, typer.Option("--params", "-p", help='策略参数（JSON格式）')] = "{}",
    data: Annotated[Optional[str], typer.Option("--data", "-d", help="数据文件路径（CSV格式）")] = None,
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
    no_progress: Annotated[bool, typer.Option("--no-progress", help="不显示进度条")] = False
):
    """
    运行回测
    """
    # 设置日志
    log_file = get_default_log_file() if verbose else None
    setup_logger(level="DEBUG" if verbose else "INFO", log_file=log_file, simple_console=not verbose)
    
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
    if data:
        # 从文件加载数据
        print(f"从文件加载数据: {data}")
        try:
            import pandas as pd
            df = pd.read_csv(data, index_col=0, parse_dates=True)
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
                show_progress=not no_progress
            )
            
            # 报告下载结果摘要
            failed_results = [r for r in download_results if not r.success]
            no_data_failures = [r for r in failed_results 
                              if r.failure_type == DownloadFailureType.NO_DATA_AVAILABLE]
            
            if no_data_failures:
                print(f"\n⚠️ 以下 {len(no_data_failures)} 个货币对数据源无可用数据，已跳过:")
                for result in no_data_failures:
                    print(f"  - {result.symbol} {result.timeframe}")
            
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
        if download_failures:
            results['_download_failures'] = download_failures
        
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
