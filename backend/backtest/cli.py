"""
回测CLI模块

提供命令行界面用于运行和管理回测任务。
本模块只负责参数解析和调用服务层，不包含复杂业务逻辑。
所有回测均使用事件驱动引擎（axon-quant）。
"""

import json
import sys
from pathlib import Path
from typing import Optional

import typer
from typer import Typer, Option
from typing import Annotated
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from utils.logger import get_logger, LogType


# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)

# 创建Typer应用实例
app = typer.Typer(
    name="backtest",
    help="QuantCell 回测工具（事件驱动引擎 axon-quant）",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich"
)


# 导入服务层（延迟导入避免循环依赖）
def _get_data_provider():
    from backtest.data_provider import BacktestDataProvider
    return BacktestDataProvider()


def _get_engine_service(data_provider):
    from backtest.engine_service import EventDrivenBacktestService
    return EventDrivenBacktestService(data_provider)


@app.command()
def run(
    strategy: Annotated[str, Option("--strategy", "-s", help="策略名称或路径")],
    params: Annotated[str, Option("--params", "-p", help="策略参数JSON字符串")] = "{}",
    symbols: Annotated[str, Option("--symbols", "--sym", help="交易对列表，逗号分隔")] = "BTCUSDT",
    timeframes: Annotated[str, Option("--timeframes", "--tf", help="时间周期列表，逗号分隔")] = "1h",
    initial_capital: Annotated[float, Option("--initial-capital", "--cash", help="初始资金")] = 10000,
    commission: Annotated[float, Option("--commission", "-c", help="手续费率")] = 0.001,
    base_currency: Annotated[str, Option("--base-currency", help="基础货币")] = "USDT",
    leverage: Annotated[float, Option("--leverage", help="杠杆倍数")] = 1.0,
    time_range: Annotated[Optional[str], Option("--time-range", help="时间范围(YYYYMMDD-YYYYMMDD)")] = None,
    output_format: Annotated[str, Option("--output-format", "-o", help="输出格式(json/table/both)")] = "table",
    output_file: Annotated[Optional[str], Option("--output-file", "-f", help="输出文件路径")] = None,
):
    """
    运行回测（使用事件驱动引擎 axon-quant）
    
    示例:
      # 基本回测
      uv run python -m cli.backtest run --strategy sma_crossover --symbols BTCUSDT --timeframes 1h

      # 自定义初始资金
      uv run python -m cli.backtest run --strategy sma_crossover --initial-capital 100000

      # 多品种回测
      uv run python -m cli.backtest run --strategy sma_crossover --symbols BTCUSDT,ETHUSDT --timeframes 1h
    """
    console = Console()
    
    try:
        # 解析参数
        strategy_params = json.loads(params)
        symbols_list = [s.strip() for s in symbols.split(",")]
        timeframes_list = [t.strip() for t in timeframes.split(",")]
        
        console.print(f"\n[bold blue]🚀 开始执行回测[/bold blue]")
        console.print(f"   策略: {strategy}")
        console.print(f"   品种: {', '.join(symbols_list)}")
        console.print(f"   周期: {', '.join(timeframes_list)}")
        console.print(f"   引擎: 事件驱动 (axon-quant)")
        
        # 初始化服务
        data_provider = _get_data_provider()
        service = _get_engine_service(data_provider)
        
        results = service.run_backtest(
            strategy_name=strategy,
            strategy_params=strategy_params,
            symbols=symbols_list,
            timeframes=timeframes_list,
            engine_config={
                "initial_capital": initial_capital,
                "base_currency": base_currency,
                "leverage": leverage,
                "time_range": time_range,
                "log_level": "WARNING"
            },
            show_progress=True
        )
        
        # 输出结果
        _output_results(results, output_format, output_file, console)
        
    except json.JSONDecodeError as e:
        logger.error(f"策略参数解析失败: {e}")
        console.print(f"[red]❌ 策略参数JSON格式错误: {e}[/red]")
        raise typer.Exit(1)
    
    except FileNotFoundError as e:
        logger.error(f"数据文件未找到: {e}")
        console.print(f"[red]❌ 数据文件未找到: {e}[/red]")
        console.print("[yellow]💡 提示: 请先使用 data_cli.py download 下载数据[/yellow]")
        raise typer.Exit(1)
    
    except Exception as e:
        logger.exception(f"回测执行失败: {e}")
        console.print(f"[red]❌ 回测失败: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def list_strategies(
    verbose: Annotated[bool, Option("-v/--verbose", help="显示详细信息")] = False,
):
    """列出所有可用策略"""
    console = Console()
    
    strategies_dir = Path(__file__).resolve().parent.parent / 'strategies'
    
    if not strategies_dir.exists():
        console.print("[red]❌ 策略目录不存在[/red]")
        return
    
    strategy_files = sorted(list(strategies_dir.glob("*.py")))
    
    if not strategy_files:
        console.print("[yellow]⚠️ 未找到任何策略文件[/yellow]")
        return
    
    table = Table(title=f"📋 可用策略 (共{len(strategy_files)}个)")
    table.add_column("策略名称", style="cyan")
    table.add_column("类型", style="green")
    table.add_column("描述", style="white")

    # 延迟导入基类，避免启动时加载依赖
    try:
        from backtest.strategies.event_strategy import EventDrivenStrategy
    except Exception:
        EventDrivenStrategy = None

    for strategy_file in strategy_files:
        strategy_name = strategy_file.stem

        strategy_type = "未知"
        description = ""

        try:
            module_path = str(strategy_file.parent)
            if module_path not in sys.path:
                sys.path.insert(0, module_path)

            import importlib
            spec = importlib.util.spec_from_file_location(strategy_name, str(strategy_file))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # 检查是否包含 EventDrivenStrategy 子类（实际策略）
            has_event_strategy = False
            has_base_class = False

            for attr_name in dir(module):
                attr_val = getattr(module, attr_name)
                if isinstance(attr_val, type):
                    if EventDrivenStrategy is not None:
                        if issubclass(attr_val, EventDrivenStrategy) and attr_val is not EventDrivenStrategy:
                            has_event_strategy = True
                    if attr_name in ('EventDrivenStrategy', 'EventDrivenStrategyConfig'):
                        has_base_class = True

            if has_event_strategy:
                strategy_type = "[cyan]事件驱动[/cyan]"
            elif has_base_class:
                strategy_type = "[green]策略基类[/green]"
            else:
                strategy_type = "[yellow]未分类[/yellow]"

            doc = getattr(module, '__doc__', '')
            if doc:
                first_line = doc.strip().split('\n')[0]
                description = first_line[:60] + ('...' if len(first_line) > 60 else '')

        except Exception as e:
            if verbose:
                description = f"[red]加载错误: {str(e)[:40]}...[/red]"

        table.add_row(strategy_name, strategy_type, description)
    
    console.print(table)
    
    if verbose:
        console.print("\n[yellow]💡 提示: 使用 'run' 命令执行回测[/yellow]")


@app.command()
def plot(
    input_file: Annotated[str, Option("--input-file", "-i", help="输入结果文件")],
    output_format: Annotated[str, Option("--format", "-o", help="输出格式(png/html/svg)")] = "html",
    output_dir: Annotated[str, Option("--output-dir", "-d", help="输出目录")] = "./backtest_results",
):
    """绘制回测结果图表"""
    console = Console()
    
    input_path = Path(input_file)
    
    if not input_path.exists():
        console.print(f"[red]❌ 输入文件不存在: {input_file}[/red]")
        raise typer.Exit(1)
    
    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            results = json.load(f)
        
        from backtest.plot_utils import plot_backtest_results
        from backtest.result_analysis import output_results
        
        plot_path = plot_backtest_results(results, output_format=output_format, output_dir=output_dir)
        
        console.print(f"\n[bold green]✅ 图表生成成功![/bold green]")
        console.print(f"📍 输出路径: {plot_path}")
        
        if output_format == "html":
            import webbrowser
            webbrowser.open('file://' + str(Path(plot_path).absolute()))
            
    except Exception as e:
        logger.error(f"绘制图表失败: {e}")
        console.print(f"[red]❌ 绘制失败: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def show(
    result_id: Annotated[int, Option("--id", help="结果ID")] = None,
    latest: Annotated[bool, Option("--latest/-l", help="显示最新结果")] = True,
):
    """显示回测结果详情"""
    console = Console()
    
    try:
        from backtest.service import BacktestService
        service = BacktestService()
        
        if result_id:
            result = service.get_result(result_id)
        elif latest:
            result = service.get_latest_result()
        else:
            results = service.get_result_list(limit=10)
            
            table = Table(title="最近10次回测结果")
            table.add_column("ID", style="cyan")
            table.add_column("策略", style="green")
            table.add_column("品种", style="white")
            table.add_column("时间", style="yellow")
            table.add_column("状态", style="magenta")
            
            for r in results[:10]:
                status_style = "green" if r.get('status') == 'completed' else "red"
                table.add_row(
                    str(r.get('id', '-')),
                    r.get('strategy_name', '-'),
                    r.get('symbols', '-'),
                    r.get('created_at', '-')[:19],
                    f"[{status_style}]{r.get('status', '-')}[/{status_style}]"
                )
            
            console.print(table)
            return
        
        if not result:
            console.print("[yellow]⚠️ 未找到回测结果[/yellow]")
            return
        
        _output_results(result, "table", None, console)
        
    except Exception as e:
        logger.error(f"显示结果失败: {e}")
        console.print(f"[red]❌ 显示失败: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def compare(
    result_ids: Annotated[str, Option("--ids", help="要比较的结果ID列表，逗号分隔")] = "",
    latest_n: Annotated[int, Option("--latest-n", "-n", help="比较最近的N个结果")] = 5,
):
    """对比多个回测结果"""
    console = Console()
    
    try:
        from backtest.service import BacktestService
        service = BacktestService()
        
        if result_ids:
            ids = [int(id.strip()) for id in result_ids.split(",")]
        else:
            all_results = service.get_result_list(limit=latest_n)
            ids = [r['id'] for r in all_results]
        
        if len(ids) < 2:
            console.print("[yellow]⚠️ 至少需要2个结果才能进行对比[/yellow]")
            return
        
        results = [service.get_result(id) for id in ids]
        
        table = Table(title=f"📊 回测结果对比 ({len(ids)}个)")
        table.add_column("ID", style="cyan")
        table.add_column("策略", style="green")
        table.add_column("收益率%", justify="right", style="white")
        table.add_column("胜率%", justify="right", style="yellow")
        table.add_column("交易次数", justify="right", style="magenta")
        table.add_column("最大回撤%", justify="right", style="red")
        
        for r in results:
            metrics = r.get('portfolio', {}).get('metrics', {})
            
            table.add_row(
                str(r.get('_meta', {}).get('timestamp', '-')),
                r.get('_meta', {}).get('strategy', '-'),
                f"{metrics.get('total_return', 0):.2f}",
                f"{metrics.get('win_rate', 0):.2f}",
                str(metrics.get('total_trades', 0)),
                f"{metrics.get('max_drawdown', 0):.2f}"
            )
        
        console.print(table)
        
    except Exception as e:
        logger.error(f"对比结果失败: {e}")
        console.print(f"[red]❌ 对比失败: {e}[/red]")
        raise typer.Exit(1)


def _output_results(results: dict, output_format: str, output_file: Optional[str], console: Console):
    """
    格式化并输出回测结果

    Args:
        results: 回测结果字典
        output_format: 输出格式 (json/table/both)
        output_file: 输出文件路径（可选，默认保存到 logs/backtest/）
        console: Rich控制台实例
    """
    from datetime import datetime

    # 确定输出目录：统一保存到 logs/backtest/
    backend_dir = Path(__file__).resolve().parent.parent
    default_output_dir = backend_dir / "logs" / "backtest"

    if not output_file:
        # 自动创建子目录（如果不存在）
        default_output_dir.mkdir(parents=True, exist_ok=True)

        # 生成带时间戳的文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 从结果中提取策略名称和交易对作为文件名的一部分
        strategy_name = "unknown"
        symbols = "unknown"

        if isinstance(results, dict):
            strategy_name = results.get("_meta", {}).get("strategy", "unknown")
            symbols = results.get("_meta", {}).get("symbols", ["unknown"])
            if isinstance(symbols, list):
                symbols = "_".join(symbols[:3])
            elif isinstance(symbols, str):
                symbols = symbols.replace(",", "_")[:20]

        safe_strategy = "".join(c for c in str(strategy_name) if c.isalnum() or c in ['_', '-'])[:30]
        safe_symbols = "".join(c for c in str(symbols) if c.isalnum() or c in ['_', '-'])[:20]

        output_file = str(default_output_dir / f"{timestamp}_{safe_strategy}_{safe_symbols}.json")

        logger.info(f"[回测结果] 自动保存到: {output_file}")

    else:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

    # 保存JSON（直接序列化，兼容不同格式）
    if output_format in ("json", "both"):
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False, default=str)
            output_path_full = Path(output_file).resolve()
            console.print(f"\n[bold green]✅ 结果已保存到: {output_path_full}[/bold green]")
        except Exception as e:
            logger.error(f"[回测结果] 保存失败: {e}")
            console.print(f"\n[red]❌ 保存失败: {e}[/red]")

    # 表格输出（兼容扁平结构和嵌套结构）
    if output_format in ("table", "both"):
        _print_results_table(results, console)


def _print_results_table(results: dict, console: Console):
    """以表格形式输出回测结果，兼容不同的结果结构"""
    if not isinstance(results, dict):
        console.print(f"[yellow]无效的结果格式[/yellow]")
        return

    # 检查是否为扁平结构（新的简单引擎结果）
    if 'total_return' in results or 'final_equity' in results:
        # 扁平结构：直接显示指标
        _print_flat_results(results, console)
        return

    # 嵌套结构（事件驱动引擎结果）
    try:
        from backtest.result_analysis import output_results as ra_output
        ra_output(results, output_format='table', output_file=None)
    except Exception as e:
        logger.warning(f"使用标准输出失败: {e}")
        # 降级输出
        console.print_json(data=results)


def _print_flat_results(results: dict, console: Console):
    """输出扁平结构的回测结果表格"""
    table = Table(title="回测结果", show_header=True, header_style="bold magenta")
    table.add_column("指标", style="cyan")
    table.add_column("数值", style="green")

    table.add_row("初始资金", f"{results.get('initial_cash', 0):.2f}")
    table.add_row("最终权益", f"{results.get('final_equity', 0):.2f}")
    table.add_row("总收益率", f"{results.get('total_return', 0):.2%}")
    table.add_row("最大回撤", f"{results.get('max_drawdown', 0):.2%}")
    table.add_row("夏普比率", f"{results.get('sharpe_ratio', 0):.4f}")
    table.add_row("总交易次数", str(results.get('total_trades', 0)))
    table.add_row("盈利次数", str(results.get('winning_trades', 0)))
    table.add_row("亏损次数", str(results.get('losing_trades', 0)))
    table.add_row("胜率", f"{results.get('win_rate', 0):.2%}")
    table.add_row("处理K线数", str(results.get('bars_processed', 0)))

    console.print(table)


if __name__ == "__main__":
    app()
