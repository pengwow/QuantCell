"""
回测CLI模块

提供命令行界面用于运行和管理回测任务。
本模块只负责参数解析和调用服务层，不包含复杂业务逻辑。
"""

import importlib
import importlib.util
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
    help="QuantCell 回测工具",
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
    # 末日单管理(回测结束 EOD 强制平仓,适合日报/对账场景)
    force_liquidate: Annotated[bool, Option("--force-liquidate/--no-force-liquidate", help="回测结束强制市价平仓所有未平仓持仓(末日单管理,适合日报/对账)")] = False,
    # 多数据类型支持
    data_type: Annotated[str, Option("--data-type", "-dt", help="数据类型: kline/aggTrades/trades/bookDepth/bookTicker/fundingRate/openInterest/markPriceKlines/indexPriceKlines/premiumIndexKlines")] = "kline",
    market: Annotated[str, Option("--market", "-mkt", help="市场类型: spot/um/cm")] = "spot",
    chart: Annotated[bool, Option("--chart/--no-chart", help="生成回测图表")] = False,
    output_format: Annotated[str, Option("--output-format", "-o", help="输出格式(json/table/both)")] = "table",
    output_file: Annotated[Optional[str], Option("--output-file", "-f", help="输出文件路径")] = None,
):
    """
    运行回测

    示例:
      # 默认 K线回测
      uv run python -m cli.backtest run --strategy sma_cross_strategy --symbols BTCUSDT --timeframes 1h

      # 使用 aggTrades Tick 数据回测
      uv run python -m cli.backtest run --strategy sma_cross_strategy --symbols BTCUSDT --data-type aggTrades

      # 使用 fundingRate 衍生数据回测 (需先下载 markPriceKlines + fundingRate)
      uv run python -m cli.backtest run --strategy funding_arbitrage --symbols BTCUSDT --data-type fundingRate --market um

      # 启用 EOD 强制平仓(末日单管理:所有 PnL 转为已实现,适合日报/对账)
      uv run python -m cli.backtest run --strategy sma_cross_strategy --symbols BTCUSDT --timeframes 1h --force-liquidate

      # 多品种回测
      uv run python -m cli.backtest run --strategy sma_cross_axon --symbols BTCUSDT,ETHUSDT --timeframes 1h
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
        console.print(f"   数据类型: {data_type}")
        console.print(f"   市场: {market}")
        # 末日单状态(便于用户确认回测语义)
        if force_liquidate:
            console.print(f"   末日单: [yellow]强制平仓[/yellow] (EOD 市价清仓,PnL 全部转为已实现)")
        else:
            console.print(f"   末日单: [green]保留持仓[/green] (按末帧 mark 估值,忠实策略意图)")

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
                "log_level": "WARNING",
                # 透传到 EventDrivenBacktestService.run_backtest → BacktestEngine → BacktestLoop
                "force_liquidate": force_liquidate,
            },
            show_progress=True,
            data_type=data_type,
            market=market,
        )

        # 输出结果
        _output_results(results, output_format, output_file, console)

        # 生成图表
        if chart:
            try:
                chart_path = _generate_chart(results, console)
                if chart_path:
                    console.print(f"[bold green]📊 图表已保存: {chart_path}[/bold green]")
            except Exception as e:
                console.print(f"[yellow]⚠️ 图表生成失败: {e}[/yellow]")

    except json.JSONDecodeError as e:
        logger.error(f"策略参数解析失败: {e}")
        console.print(f"[red]❌ 策略参数JSON格式错误: {e}[/red]")
        raise typer.Exit(1)

    except FileNotFoundError as e:
        logger.error(f"数据文件未找到: {e}")
        console.print(f"[red]❌ 数据文件未找到: {e}[/red]")
        console.print("[yellow]💡 提示: 请先使用 cli.data download 下载数据[/yellow]")
        raise typer.Exit(1)

    except Exception as e:
        logger.exception(f"回测执行失败: {e}")
        console.print(f"[red]❌ 回测失败: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def list_strategies(
    verbose: Annotated[bool, Option("-v/--verbose", help="显示详细信息")] = False,
):
    """列出所有可用策略

    扫描所有策略目录（包括 example 目录和旧版 strategies 目录），
    与 `run -s <name>` 使用的查找路径完全一致。
    """
    console = Console()

    # 使用 StrategyLoaderService 的单一真相源，与 run -s 保持一致
    from backtest.strategy_loader_service import StrategyLoaderService

    strategy_files = StrategyLoaderService.get_all_strategy_files()

    if not strategy_files:
        console.print("[yellow]⚠️ 未找到任何策略文件[/yellow]")
        return

    table = Table(title=f"📋 可用策略 (共{len(strategy_files)}个)")
    table.add_column("策略名称", style="cyan")
    table.add_column("类型", style="green")
    table.add_column("描述", style="white")
    table.add_column("位置", style="dim")

    for strategy_file in strategy_files:
        strategy_name = strategy_file.stem

        strategy_type = "未知"
        description = ""
        location = strategy_file.parent.name

        try:
            spec = importlib.util.spec_from_file_location(strategy_name, str(strategy_file))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # 检测策略类型
            source = ""
            try:
                source = open(strategy_file, encoding="utf-8").read()
            except Exception:
                pass

            is_rl = ("TradingEnv" in source or "stable_baselines3" in source or
                     "from rl." in source or "model.predict" in source)
            has_on_bar = any(
                isinstance(getattr(module, attr), type) and
                hasattr(getattr(module, attr), "on_bar")
                for attr in dir(module)
                if not attr.startswith("_")
            )

            if is_rl:
                strategy_type = "[magenta]RL 策略[/magenta]"
            elif has_on_bar:
                strategy_type = "[green]规则策略[/green]"
            else:
                strategy_type = "[blue]未知[/blue]"

            doc = getattr(module, '__doc__', '')
            if doc:
                first_line = doc.strip().split('\n')[0]
                description = first_line[:60] + ('...' if len(first_line) > 60 else '')

        except Exception as e:
            if verbose:
                description = f"[red]加载错误: {str(e)[:40]}...[/red]"

        table.add_row(strategy_name, strategy_type, description, location)

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
                f"{metrics.get('win_rate', 0) * 100:.4f}",
                str(metrics.get('total_trades', 0)),
                f"{metrics.get('max_drawdown', 0) * 100:.4f}"
            )
        
        console.print(table)
        
    except Exception as e:
        logger.error(f"对比结果失败: {e}")
        console.print(f"[red]❌ 对比失败: {e}[/red]")
        raise typer.Exit(1)


def _generate_chart(results: dict, console: Console) -> Optional[str]:
    """
    生成回测图表（资金曲线、回撤、月度交易、单笔盈亏）

    Args:
        results: 回测结果字典
        console: Rich控制台实例

    Returns:
        图表文件路径，失败返回 None
    """
    try:
        import numpy as np
        import pandas as pd
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        console.print("[yellow]⚠️ 需要安装 matplotlib: pip install matplotlib[/yellow]")
        return None

    # 从结果中提取数据
    portfolio = results.get("portfolio", {})
    equity_curve = results.get("equity_curve") or portfolio.get("equity_curve", [])
    trade_records = results.get("trades") or portfolio.get("trades", [])
    trade_records = results.get("trade_records") or trade_records
    meta = results.get("_meta", {})
    strategy_name = meta.get("strategy", "Strategy")
    symbols = meta.get("symbols", ["BTCUSDT"])
    symbol = symbols[0] if isinstance(symbols, list) else symbols

    if not equity_curve:
        console.print("[yellow]⚠️ 无权益曲线数据，跳过图表生成[/yellow]")
        return None

    # 转换数据
    eq_data = np.array(equity_curve)
    if eq_data.ndim == 2:
        timestamps = eq_data[:, 0]
        equity = eq_data[:, 1]
    else:
        equity = eq_data
        timestamps = np.arange(len(equity))

    # 转换时间戳为日期
    try:
        ts_dates = pd.to_datetime(timestamps, unit='ns')
    except Exception:
        ts_dates = pd.RangeIndex(len(equity))

    equity_series = pd.Series(equity, index=ts_dates)

    # 交易数据
    trades_df = pd.DataFrame(trade_records) if trade_records else pd.DataFrame()

    # 统计指标
    total_pnl = equity[-1] - equity[0]
    pnl_pct = total_pnl / equity[0] * 100
    peak = equity_series.cummax()
    drawdown = (equity_series - peak) / peak * 100
    max_dd = drawdown.min()

    # 年化夏普
    returns = equity_series.pct_change().dropna()
    sharpe = returns.mean() / (returns.std() + 1e-8) * np.sqrt(96 * 365) if len(returns) > 1 else 0

    # 创建图表
    fig, axes = plt.subplots(4, 1, figsize=(14, 16),
                             gridspec_kw={'height_ratios': [3, 1.5, 1, 1]})
    fig.suptitle(
        f'{symbol} PPO Backtest\n'
        f'PnL: {"+" if total_pnl >= 0 else ""}{total_pnl:,.0f} ({pnl_pct:+.1f}%) | '
        f'Sharpe: {sharpe:.2f} | MaxDD: {abs(max_dd):.2f}%',
        fontsize=14, fontweight='bold'
    )

    # 1. 资金曲线
    ax1 = axes[0]
    ax1.plot(ts_dates, equity, color='#2ecc71', linewidth=1.2, label='Portfolio')
    ax1.axhline(y=equity[0], color='black', linestyle='--', alpha=0.3)
    ax1.fill_between(ts_dates, equity[0], equity,
                      where=equity >= equity[0], alpha=0.1, color='green')
    ax1.fill_between(ts_dates, equity[0], equity,
                      where=equity < equity[0], alpha=0.1, color='red')
    ax1.set_ylabel('Value ($)')
    ax1.set_title('Equity Curve')
    ax1.legend(loc='upper left')

    # 标注极值
    peak_i = np.argmax(equity)
    trough_i = np.argmin(equity)
    ax1.annotate(f'Peak ${equity[peak_i]:,.0f}',
                 xy=(ts_dates[peak_i], equity[peak_i]),
                 xytext=(10, 10), textcoords='offset points', fontsize=8,
                 color='green', arrowprops=dict(arrowstyle='->', color='green'))
    ax1.annotate(f'Low ${equity[trough_i]:,.0f}',
                 xy=(ts_dates[trough_i], equity[trough_i]),
                 xytext=(10, -15), textcoords='offset points', fontsize=8,
                 color='red', arrowprops=dict(arrowstyle='->', color='red'))

    # 2. 回撤
    ax2 = axes[1]
    ax2.fill_between(ts_dates, 0, drawdown.values, color='crimson', alpha=0.3)
    ax2.plot(ts_dates, drawdown.values, color='crimson', linewidth=0.6)
    ax2.set_ylabel('Drawdown (%)')
    ax2.set_title('Drawdown')
    ax2.set_ylim(min(drawdown.values) * 1.3, 0.5)

    # 3. 月度交易
    ax3 = axes[2]
    if not trades_df.empty and 'time' in trades_df.columns:
        trades_df['time'] = pd.to_datetime(trades_df['time'])
        trades_df['month'] = trades_df['time'].dt.to_period('M')
        monthly = trades_df.groupby('month').agg(
            buys=('action', lambda x: (x == 'BUY').sum()),
            sells=('action', lambda x: (x == 'SELL').sum()),
        )
        x = np.arange(len(monthly))
        ax3.bar(x - 0.2, monthly['buys'].values, 0.4, label='BUY', color='#2ecc71', alpha=0.7)
        ax3.bar(x + 0.2, monthly['sells'].values, 0.4, label='SELL', color='#e74c3c', alpha=0.7)
        ax3.set_xticks(x)
        ax3.set_xticklabels([str(p) for p in monthly.index], rotation=45, fontsize=7)
        ax3.set_ylabel('Count')
        ax3.set_title('Monthly Trades')
        ax3.legend()
    else:
        ax3.text(0.5, 0.5, 'No trade data', ha='center', va='center', transform=ax3.transAxes)
        ax3.set_title('Monthly Trades')

    # 4. 单笔盈亏
    ax4 = axes[3]
    if not trades_df.empty and 'portfolio' in trades_df.columns:
        pnl = trades_df['portfolio'].diff().fillna(0).values
        colors = ['#2ecc71' if x >= 0 else '#e74c3c' for x in pnl]
        ax4.bar(range(len(pnl)), pnl, color=colors, alpha=0.5, width=1.0)
        ax4.axhline(0, color='black', linestyle='--', alpha=0.3)
        if len(pnl) > 20:
            ma = pd.Series(pnl).rolling(20).mean()
            ax4.plot(range(len(ma)), ma.values, color='blue', linewidth=1, label='MA20')
            ax4.legend()
    else:
        ax4.text(0.5, 0.5, 'No trade data', ha='center', va='center', transform=ax4.transAxes)
    ax4.set_ylabel('PnL ($)')
    ax4.set_title('Per-Trade PnL')

    plt.tight_layout()

    # 保存图表
    backend_dir = Path(__file__).resolve().parent.parent
    chart_dir = backend_dir / "logs" / "backtest"
    chart_dir.mkdir(parents=True, exist_ok=True)

    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = "".join(c for c in strategy_name if c.isalnum() or c in ['_', '-'])[:20]
    chart_path = str(chart_dir / f"{timestamp}_{safe_name}_{symbol}_chart.png")

    plt.savefig(chart_path, dpi=150, bbox_inches='tight')
    plt.close()

    return chart_path


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
                symbols = "_".join(symbols[:3])  # 取前3个品种
            elif isinstance(symbols, str):
                symbols = symbols.replace(",", "_")[:20]

        safe_strategy = "".join(c for c in str(strategy_name) if c.isalnum() or c in ['_', '-'])[:30]
        safe_symbols = "".join(c for c in str(symbols) if c.isalnum() or c in ['_', '-'])[:20]

        output_file = str(default_output_dir / f"{timestamp}_{safe_strategy}_{safe_symbols}.json")

        logger.info(f"[回测结果] 自动保存到: {output_file}")

    else:
        # 用户指定了路径，确保目录存在
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

    from backtest.result_analysis import output_results

    if output_format in ("json", "both"):
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False, default=str)
            output_path_full = Path(output_file).resolve()
            console.print(f"\n[bold green]✅ 结果已保存到: {output_path_full}[/bold green]")
        except Exception as e:
            logger.error(f"[回测结果] 保存失败: {e}")
            console.print(f"\n[red]❌ 保存失败: {e}[/red]")

    if output_format in ("table", "both"):
        output_results(results)


if __name__ == "__main__":
    app()
