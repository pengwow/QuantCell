#!/usr/bin/env python3
"""
QuantCell 策略验证与回测对比脚本

此脚本用于：
1. 验证策略文件的有效性与格式规范性
2. 在QuantCell、Backtrader、Freqtrade三个框架中执行回测
3. 对比回测结果，确保一致性
4. 生成详细的回测对比报告
5. 支持从CSV/TXT文件加载数据，自动处理字段名格式

使用方法：
    # 验证策略
    python scripts/validate_strategy.py validate --strategy sma_crossover_quantcell

    # 执行回测对比（使用在线数据）
    python scripts/validate_strategy.py backtest --strategy sma_crossover_quantcell --symbol BTC/USDT

    # 执行回测对比（使用本地数据文件）
    python scripts/validate_strategy.py backtest --strategy sma_crossover_quantcell --data-file ./data/btc.csv

    # 生成详细报告
    python scripts/validate_strategy.py backtest --strategy sma_crossover_quantcell --detailed --output report.md

数据文件格式支持：
    - CSV格式 (.csv) 或 TXT格式 (.txt)
    - 支持的分隔符：逗号、制表符、分号、竖线
    - 自动识别字段名（支持大小写不敏感和中文字段名）
    - 必需字段：Open/High/Low/Close（或其变体如开盘价/最高价等）
    - 可选字段：Volume/Date（或其变体如成交量/日期等）

支持的字段名映射：
    - Open: open, OPEN, Open, 开盘价, 开盘
    - High: high, HIGH, High, 最高价
    - Low: low, LOW, Low, 最低价
    - Close: close, CLOSE, Close, 收盘价, adj_close, 收盘
    - Volume: volume, VOLUME, Volume, 成交量, vol
    - Date: date, DATE, Date, 日期, datetime, timestamp
"""

import sys
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import importlib.util
import inspect

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
import pandas as pd
import numpy as np

# 添加backend到路径
backend_path = Path(__file__).resolve().parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from scripts.backtest_adapters import (
    QuantCellAdapter,
    BacktraderAdapter,
    FreqtradeAdapter,
    BacktestResult
)

# 创建typer应用
app = typer.Typer(
    name="validate_strategy",
    help="QuantCell 策略验证与回测对比工具",
    add_completion=False,
)

console = Console()


def load_strategy(strategy_name: str) -> tuple[type, str]:
    """
    加载策略类
    
    Args:
        strategy_name: 策略名称（不含.py后缀）
        
    Returns:
        tuple[type, str]: (策略类, 错误信息)
    """
    strategy_path = backend_path / "strategies" / f"{strategy_name}.py"
    
    if not strategy_path.exists():
        return None, f"策略文件不存在: {strategy_path}"
    
    try:
        # 动态加载模块
        spec = importlib.util.spec_from_file_location(strategy_name, strategy_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        # 查找策略类
        for name, obj in inspect.getmembers(module):
            if inspect.isclass(obj) and name not in ['StrategyCore', 'StrategyBase']:
                # 检查是否是策略类
                if hasattr(obj, 'calculate_indicators') or hasattr(obj, 'on_bar'):
                    return obj, ""
        
        return None, "未找到策略类"
        
    except Exception as e:
        return None, f"加载策略失败: {e}"


def load_and_normalize_data(file_path: str) -> pd.DataFrame:
    """
    加载并标准化数据文件

    支持CSV和TXT格式，处理字段名的大小写和命名差异
    自动检测无表头文件和毫秒级时间戳

    Args:
        file_path: 数据文件路径

    Returns:
        pd.DataFrame: 标准化的数据框，包含Open, High, Low, Close, Volume列

    Raises:
        ValueError: 当文件格式不支持或缺少必需列时
    """
    file_path = Path(file_path)

    if not file_path.exists():
        raise ValueError(f"数据文件不存在: {file_path}")

    # 根据扩展名读取文件
    suffix = file_path.suffix.lower()

    try:
        if suffix == '.csv':
            # 先尝试读取，不指定表头，让pandas自动检测
            df = pd.read_csv(file_path, header=None)
        elif suffix == '.txt':
            # 尝试不同的分隔符
            for sep in [',', '\t', ';', '|']:
                try:
                    df = pd.read_csv(file_path, sep=sep, header=None)
                    if len(df.columns) > 1:
                        break
                except:
                    continue
            else:
                raise ValueError("无法解析TXT文件，请确保使用逗号、制表符、分号或竖线分隔")
        else:
            raise ValueError(f"不支持的文件格式: {suffix}，请使用CSV或TXT文件")

    except Exception as e:
        raise ValueError(f"读取数据文件失败: {e}")

    # 检测是否有表头（第一行是否为数字）
    first_row = df.iloc[0]
    has_header = False

    # 检查第一行第一个值是否为时间戳（数字）
    try:
        first_val = str(first_row[0]).strip()
        # 如果是纯数字（可能是时间戳），则无表头
        if first_val.replace('.', '').replace('-', '').isdigit():
            has_header = False
        else:
            has_header = True
    except:
        has_header = True

    if not has_header:
        # 无表头，根据列数自动分配列名
        num_cols = len(df.columns)
        if num_cols >= 6:
            # 标准OHLCV格式: timestamp, open, high, low, close, volume, [symbol]
            column_names = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
            if num_cols > 6:
                column_names.extend([f'col_{i}' for i in range(6, num_cols)])
        elif num_cols == 5:
            # 可能是: timestamp, open, high, low, close (无volume)
            column_names = ['timestamp', 'open', 'high', 'low', 'close']
        else:
            raise ValueError(f"数据文件列数不足，期望至少5列，实际{num_cols}列")

        df.columns = column_names
        original_columns = column_names
        console.print(f"[yellow]检测到无表头文件，自动分配列名: {column_names[:num_cols]}[/yellow]")
    else:
        # 有表头，重新读取
        if suffix == '.csv':
            df = pd.read_csv(file_path)
        else:
            for sep in [',', '\t', ';', '|']:
                try:
                    df = pd.read_csv(file_path, sep=sep)
                    if len(df.columns) > 1:
                        break
                except:
                    continue
        original_columns = df.columns.tolist()

    # 标准化列名（转换为小写并去除空格）
    df.columns = [str(col).strip().lower().replace(' ', '_') for col in df.columns]

    # 定义字段名映射（支持多种命名方式）
    column_mapping = {
        # Open 列映射
        'open': 'Open',
        'opening': 'Open',
        'opening_price': 'Open',
        'open_price': 'Open',
        '开盘价': 'Open',
        '开盘': 'Open',

        # High 列映射
        'high': 'High',
        'highest': 'High',
        'high_price': 'High',
        'highest_price': 'High',
        '最高价': 'High',

        # Low 列映射
        'low': 'Low',
        'lowest': 'Low',
        'low_price': 'Low',
        'lowest_price': 'Low',
        '最低价': 'Low',

        # Close 列映射
        'close': 'Close',
        'closing': 'Close',
        'closing_price': 'Close',
        'close_price': 'Close',
        '收盘价': 'Close',
        '收盘': 'Close',
        'adj_close': 'Close',
        'adjclose': 'Close',
        'adjusted_close': 'Close',
        'adjust_close': 'Close',

        # Volume 列映射
        'volume': 'Volume',
        'vol': 'Volume',
        'volumes': 'Volume',
        '成交量': 'Volume',
        '交易量': 'Volume',
        'vols': 'Volume',

        # Date 列映射
        'date': 'Date',
        'datetime': 'Date',
        'time': 'Date',
        'timestamp': 'Date',
        'date_time': 'Date',
        'trade_date': 'Date',
        'trading_date': 'Date',
        '日期': 'Date',
        '时间': 'Date',
        '交易日期': 'Date',
    }

    # 重命名列
    rename_dict = {}
    for old_col in df.columns:
        if old_col in column_mapping:
            rename_dict[old_col] = column_mapping[old_col]

    df = df.rename(columns=rename_dict)

    # 检查必需列
    required_columns = ['Open', 'High', 'Low', 'Close']
    missing_columns = [col for col in required_columns if col not in df.columns]

    if missing_columns:
        available = [col for col in df.columns if col != 'Date']
        raise ValueError(
            f"数据文件缺少必需列: {missing_columns}\n"
            f"可用列: {available}\n"
            f"原始列: {original_columns}"
        )

    # 如果没有Volume列，添加一个默认值为0的列
    if 'Volume' not in df.columns:
        console.print("[yellow]警告: 数据文件缺少Volume列，将使用默认值0[/yellow]")
        df['Volume'] = 0

    # 处理日期列
    date_column = None
    if 'Date' in df.columns:
        date_column = 'Date'
    elif 'timestamp' in df.columns:
        date_column = 'timestamp'

    if date_column:
        # 检测是否为毫秒级时间戳（13位数字）
        first_val = df[date_column].iloc[0]
        is_millisecond = False

        try:
            # 转换为数字
            num_val = pd.to_numeric(first_val)
            # 如果是13位左右的数字，可能是毫秒时间戳
            if num_val > 1e12:  # 毫秒级时间戳大于1e12
                is_millisecond = True
        except:
            pass

        if is_millisecond:
            console.print(f"[yellow]检测到毫秒级时间戳，转换为秒级...[/yellow]")
            df[date_column] = pd.to_numeric(df[date_column]) / 1000

        # 尝试多种日期格式
        date_formats = [
            '%Y-%m-%d',
            '%Y/%m/%d',
            '%d-%m-%Y',
            '%d/%m/%Y',
            '%m-%d-%Y',
            '%m/%d/%Y',
            '%Y%m%d',
            '%Y-%m-%d %H:%M:%S',
            '%Y/%m/%d %H:%M:%S',
        ]

        date_parsed = False

        # 如果是数字（Unix时间戳），直接用pandas转换
        try:
            num_val = pd.to_numeric(df[date_column])
            if num_val.max() > 1e9:  # Unix时间戳
                df[date_column] = pd.to_datetime(num_val, unit='s')
                date_parsed = True
                console.print(f"[green]✓ 成功解析Unix时间戳[/green]")
        except:
            pass

        if not date_parsed:
            for fmt in date_formats:
                try:
                    df[date_column] = pd.to_datetime(df[date_column], format=fmt)
                    date_parsed = True
                    break
                except:
                    continue

        if not date_parsed:
            # 使用pandas自动解析
            try:
                df[date_column] = pd.to_datetime(df[date_column])
                date_parsed = True
            except:
                pass

        if date_parsed:
            df = df.set_index(date_column)
            df.index.name = 'Date'
        else:
            console.print("[yellow]警告: 无法解析日期列，将使用默认索引[/yellow]")

    # 确保数据类型正确
    numeric_columns = ['Open', 'High', 'Low', 'Close', 'Volume']
    for col in numeric_columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # 检查并处理缺失值
    for col in required_columns:
        if df[col].isnull().any():
            null_count = df[col].isnull().sum()
            console.print(f"[yellow]警告: {col}列有{null_count}个缺失值，将使用前向填充[/yellow]")
            df[col] = df[col].fillna(method='ffill').fillna(method='bfill')

    # 删除所有必需列都为NaN的行
    df = df.dropna(subset=required_columns, how='all')

    # 按日期排序
    if isinstance(df.index, pd.DatetimeIndex):
        df = df.sort_index()

    console.print(f"[green]✓ 成功加载数据文件: {len(df)}行数据[/green]")
    console.print(f"  日期范围: {df.index[0]} 至 {df.index[-1]}")

    return df


@app.command()
def validate(
    strategy: str = typer.Option(..., "--strategy", "-s", help="策略名称（不含.py后缀）"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="显示详细信息"),
):
    """
    验证策略文件的有效性与格式规范性
    
    示例：
        python scripts/validate_strategy.py validate --strategy sma_crossover_quantcell
    """
    console.print(Panel.fit(f"[bold blue]验证策略: {strategy}[/bold blue]"))
    
    # 加载策略
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("加载策略...", total=None)
        strategy_class, error = load_strategy(strategy)
        
        if strategy_class is None:
            console.print(f"[bold red]✗[/bold red] {error}")
            raise typer.Exit(1)
        
        progress.update(task, description="验证策略格式...")
        
        # 使用适配器验证
        adapters = {
            "QuantCell": QuantCellAdapter(),
            "Backtrader": BacktraderAdapter(),
            "Freqtrade": FreqtradeAdapter(),
        }
        
        results = {}
        for name, adapter in adapters.items():
            is_valid, message = adapter.validate_strategy(strategy_class)
            results[name] = (is_valid, message)
    
    # 显示验证结果
    table = Table(title="验证结果")
    table.add_column("框架", style="cyan")
    table.add_column("状态", style="bold")
    table.add_column("信息", style="dim")
    
    for name, (is_valid, message) in results.items():
        status = "[green]✓[/green]" if is_valid else "[red]✗[/red]"
        table.add_row(name, status, message if message else "通过")
    
    console.print(table)
    
    # 检查是否全部通过
    all_passed = all(is_valid for is_valid, _ in results.values())
    if all_passed:
        console.print("\n[bold green]✓ 策略验证通过！[/bold green]")
    else:
        console.print("\n[bold red]✗ 策略验证失败[/bold red]")
        raise typer.Exit(1)


@app.command()
def backtest(
    strategy: str = typer.Option(..., "--strategy", "-s", help="策略名称"),
    symbol: str = typer.Option("BTC/USDT", "--symbol", help="交易对符号"),
    timeframe: str = typer.Option("1d", "--timeframe", "-t", help="时间周期"),
    start_date: str = typer.Option(None, "--start-date", help="开始日期 (YYYY-MM-DD)"),
    end_date: str = typer.Option(None, "--end-date", help="结束日期 (YYYY-MM-DD)"),
    initial_capital: float = typer.Option(10000.0, "--capital", "-c", help="初始资金"),
    commission: float = typer.Option(0.001, "--commission", help="手续费率"),
    detailed: bool = typer.Option(False, "--detailed", "-d", help="显示详细信息"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="输出报告文件路径"),
    compare: bool = typer.Option(True, "--compare/--no-compare", help="启用对比适配"),
    data_file: Optional[str] = typer.Option(None, "--data-file", "-f", help="数据文件路径 (CSV或TXT格式)"),
):
    """
    在三个框架中执行回测并对比结果

    示例：
        python scripts/validate_strategy.py backtest --strategy sma_crossover_quantcell --symbol BTC/USDT
        python scripts/validate_strategy.py backtest --strategy sma_crossover_quantcell --detailed --output report.md
        python scripts/validate_strategy.py backtest --strategy sma_crossover_quantcell --data-file ./data/btc.csv
    """
    console.print(Panel.fit(f"[bold blue]回测对比: {strategy}[/bold blue]"))
    
    # 加载策略
    strategy_class, error = load_strategy(strategy)
    if strategy_class is None:
        console.print(f"[bold red]✗[/bold red] {error}")
        raise typer.Exit(1)
    
    # 设置日期
    if end_date is None:
        end_date = datetime.now()
    else:
        end_date = datetime.strptime(end_date, "%Y-%m-%d")
    
    if start_date is None:
        start_date = end_date - timedelta(days=365)
    else:
        start_date = datetime.strptime(start_date, "%Y-%m-%d")
    
    # 策略参数
    strategy_params = {
        'fast': 10,
        'slow': 30,
    }
    
    # 创建适配器
    adapters = {
        "QuantCell": QuantCellAdapter(),
        "Backtrader": BacktraderAdapter(),
        "Freqtrade": FreqtradeAdapter(),
    }

    results: Dict[str, BacktestResult] = {}

    # 如果提供了数据文件，先加载并标准化数据
    file_data = None
    if data_file:
        try:
            console.print(f"[bold]从文件加载数据: {data_file}[/bold]")
            file_data = load_and_normalize_data(data_file)
            # 更新日期范围
            start_date = file_data.index[0]
            end_date = file_data.index[-1]
            console.print(f"[green]✓ 数据加载完成，将使用文件数据覆盖在线数据[/green]\n")
        except Exception as e:
            console.print(f"[bold red]✗ 加载数据文件失败: {e}[/bold red]")
            raise typer.Exit(1)

    # 执行回测
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        for name, adapter in adapters.items():
            task = progress.add_task(f"在 {name} 中执行回测...", total=None)

            try:
                # 加载数据
                if file_data is not None:
                    # 使用文件数据
                    data = file_data.copy()
                else:
                    # 从在线源加载数据
                    data = adapter.load_data(symbol, start_date, end_date, timeframe)

                # 执行回测
                result = adapter.run_backtest(
                    strategy_class,
                    strategy_params,
                    data,
                    initial_capital,
                    commission,
                )

                results[name] = result
                progress.update(task, description=f"[green]✓[/green] {name} 回测完成")

            except Exception as e:
                progress.update(task, description=f"[red]✗[/red] {name} 回测失败: {e}")
                console.print(f"[red]{name} 回测失败: {e}[/red]")
    
    # 显示回测结果
    display_results(results, detailed)
    
    # 对比结果
    if compare and len(results) >= 2:
        compare_and_display(results)
    
    # 生成报告
    if output:
        generate_report(results, output, symbol, timeframe, start_date, end_date)
        console.print(f"\n[green]✓ 报告已保存到: {output}[/green]")


def display_results(results: Dict[str, BacktestResult], detailed: bool):
    """显示回测结果"""
    table = Table(title="回测结果汇总")
    table.add_column("指标", style="cyan")
    
    for name in results.keys():
        table.add_column(name, justify="right")
    
    # 添加行
    metrics = [
        ("初始资金", lambda r: f"{r.initial_capital:,.2f}" if r.initial_capital is not None else "N/A"),
        ("最终资金", lambda r: f"{r.final_capital:,.2f}" if r.final_capital is not None else "N/A"),
        ("总收益率", lambda r: f"{r.total_return_pct:.2f}%" if r.total_return_pct is not None else "N/A"),
        ("总交易次数", lambda r: str(r.total_trades) if r.total_trades is not None else "N/A"),
        ("盈利次数", lambda r: str(r.winning_trades) if r.winning_trades is not None else "N/A"),
        ("亏损次数", lambda r: str(r.losing_trades) if r.losing_trades is not None else "N/A"),
        ("胜率", lambda r: f"{r.win_rate:.2f}%" if r.win_rate is not None else "N/A"),
        ("最大回撤", lambda r: f"{r.max_drawdown_pct:.2f}%" if r.max_drawdown_pct is not None else "N/A"),
        ("夏普比率", lambda r: f"{r.sharpe_ratio:.2f}" if r.sharpe_ratio is not None else "N/A"),
    ]
    
    for metric_name, metric_func in metrics:
        row = [metric_name]
        for result in results.values():
            row.append(metric_func(result))
        table.add_row(*row)
    
    console.print(table)
    
    # 显示详细信息
    if detailed:
        for name, result in results.items():
            console.print(f"\n[bold]{name} 交易记录:[/bold]")
            
            if result.trades:
                trade_table = Table()
                trade_table.add_column("入场时间")
                trade_table.add_column("出场时间")
                trade_table.add_column("入场价格")
                trade_table.add_column("出场价格")
                trade_table.add_column("盈亏")
                trade_table.add_column("盈亏%")
                
                for trade in result.trades[:10]:  # 只显示前10条
                    trade_table.add_row(
                        trade.entry_time.strftime("%Y-%m-%d"),
                        trade.exit_time.strftime("%Y-%m-%d") if trade.exit_time else "-",
                        f"{trade.entry_price:.2f}",
                        f"{trade.exit_price:.2f}" if trade.exit_price else "-",
                        f"{trade.pnl:.2f}" if trade.pnl else "-",
                        f"{trade.pnl_pct:.2%}" if trade.pnl_pct else "-",
                    )
                
                console.print(trade_table)
            else:
                console.print("  无交易记录")


def compare_and_display(results: Dict[str, BacktestResult]):
    """对比并显示结果差异"""
    console.print("\n[bold]结果对比分析:[/bold]")
    
    # 获取第一个结果作为基准
    base_name = list(results.keys())[0]
    base_result = results[base_name]
    
    # 对比其他结果
    for name, result in results.items():
        if name == base_name:
            continue
        
        # 使用适配器对比
        adapter = QuantCellAdapter()
        comparison = adapter.compare_results(base_result, result)
        
        # 显示对比结果
        table = Table(title=f"{base_name} vs {name}")
        table.add_column("指标", style="cyan")
        table.add_column("差异", style="yellow")
        
        table.add_row("总收益率一致", "✓" if comparison['total_return_match'] else "✗")
        table.add_row("交易次数一致", "✓" if comparison['total_trades_match'] else "✗")
        table.add_row("胜率差异", f"{comparison['win_rate_diff']:.2f}%")
        table.add_row("最大回撤差异", f"{comparison['max_drawdown_diff']:.2f}%")
        table.add_row("夏普比率差异", f"{comparison['sharpe_diff']:.2f}")
        
        console.print(table)


def generate_report(results: Dict[str, BacktestResult], 
                   output_path: str,
                   symbol: str,
                   timeframe: str,
                   start_date: datetime,
                   end_date: datetime):
    """生成回测报告"""
    lines = []
    lines.append("# 回测对比报告\n")
    lines.append(f"**生成时间:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    # 回测配置
    lines.append("## 回测配置\n")
    lines.append(f"- **交易对:** {symbol}")
    lines.append(f"- **时间周期:** {timeframe}")
    lines.append(f"- **开始日期:** {start_date.strftime('%Y-%m-%d')}")
    lines.append(f"- **结束日期:** {end_date.strftime('%Y-%m-%d')}")
    lines.append(f"- **初始资金:** {list(results.values())[0].initial_capital:,.2f} USDT")
    lines.append(f"- **手续费率:** 0.1%\n")
    
    # 各框架结果
    lines.append("## 各框架回测结果\n")
    
    for name, result in results.items():
        lines.append(f"### {name}\n")
        lines.append(f"| 指标 | 数值 |")
        lines.append(f"|------|------|")
        lines.append(f"| 最终资金 | {result.final_capital:,.2f} USDT |")
        lines.append(f"| 总收益率 | {result.total_return_pct:.2f}% |")
        lines.append(f"| 总交易次数 | {result.total_trades} |")
        lines.append(f"| 盈利次数 | {result.winning_trades} |")
        lines.append(f"| 亏损次数 | {result.losing_trades} |")
        lines.append(f"| 胜率 | {result.win_rate:.2f}% |")
        lines.append(f"| 最大回撤 | {result.max_drawdown_pct:.2f}% |")
        lines.append(f"| 夏普比率 | {result.sharpe_ratio:.2f} |")
        lines.append("")
    
    # 交易记录
    lines.append("## 详细交易记录\n")
    
    for name, result in results.items():
        lines.append(f"### {name} 交易记录\n")
        
        if result.trades:
            lines.append("| 入场时间 | 出场时间 | 入场价格 | 出场价格 | 盈亏 | 盈亏% |")
            lines.append("|----------|----------|----------|----------|------|-------|")
            
            for trade in result.trades:
                entry_time = trade.entry_time.strftime("%Y-%m-%d")
                exit_time = trade.exit_time.strftime("%Y-%m-%d") if trade.exit_time else "-"
                entry_price = f"{trade.entry_price:.2f}"
                exit_price = f"{trade.exit_price:.2f}" if trade.exit_price else "-"
                pnl = f"{trade.pnl:.2f}" if trade.pnl else "-"
                pnl_pct = f"{trade.pnl_pct:.2%}" if trade.pnl_pct else "-"
                
                lines.append(f"| {entry_time} | {exit_time} | {entry_price} | {exit_price} | {pnl} | {pnl_pct} |")
        else:
            lines.append("无交易记录")
        
        lines.append("")
    
    # 写入文件
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


if __name__ == "__main__":
    app()
