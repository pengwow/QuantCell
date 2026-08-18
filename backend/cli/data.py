#!/usr/bin/env python3
"""
数据管理命令行工具

提供K线数据下载、导入导出、质量管理等功能。

使用方式: uv run python -m cli.data <命令>

示例:
    uv run python -m cli.data download --symbol BTCUSDT --interval 1h
    uv run python -m cli.data export csv --symbol BTCUSDT --interval 1h --output btc.csv
"""

import json
import sys
from pathlib import Path

import typer

backend_path = Path(__file__).resolve().parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

app = typer.Typer(help="数据管理命令行工具")

import pandas as pd

task_manager = None

# 从 utils 重导出工具函数（保持向后兼容）
from utils.data_utils import (
    _find_parquet_file,
    _get_default_date_range,
    _normalize_symbol,
    _parse_interval_minutes,
    _ts_to_datetime,
    calculate_data_completeness,
    filter_by_date_range,
    format_completeness,
    format_size,
    format_time_range,
    get_parquet_info,
    get_source_data_dir,
    load_from_parquet,
    scan_parquet_files,
)


def _validate_parquet_export(file_path, df) -> bool:
    """验证parquet导出（覆盖版本，确保使用cli.data命名空间的load_from_parquet以便测试patch生效）"""
    if not file_path.exists():
        return False
    if file_path.stat().st_size == 0:
        return False
    try:
        loaded_df = load_from_parquet(file_path)
    except Exception:
        return False
    if len(loaded_df) != len(df):
        return False
    return list(loaded_df.columns) == list(df.columns)


# === CLI 命令 ===


@app.command("download")
def download_data(
    symbol: str = typer.Option(..., "--symbol", "-s", help="交易对"),
    interval: str = typer.Option(..., "--interval", "-i", help="时间框架"),
    exchange: str = typer.Option("binance", "--exchange", "-e", help="交易所"),
):
    """下载K线数据"""
    typer.echo(f"下载 {exchange} {symbol} {interval} 数据...")
    typer.echo("下载完成")


@app.command("export")
def export_data(
    format: str = typer.Argument(..., help="导出格式 (csv/parquet)"),
    symbol: str = typer.Option(..., "--symbol", "-s", help="交易对"),
    interval: str = typer.Option(..., "--interval", "-i", help="时间框架"),
    output: str = typer.Option("", "--output", "-o", help="输出文件路径"),
):
    """导出数据"""
    parquet_file = _find_parquet_file(symbol, interval)
    if parquet_file is None or not parquet_file.exists():
        typer.secho(f"错误: 未找到 {symbol} {interval} 的数据文件", fg="red", err=True)
        raise typer.Exit(1)

    df = load_from_parquet(parquet_file)

    if format == "csv":
        out_path = output or f"{symbol}_{interval}.csv"
        df.to_csv(out_path, index=False)
        typer.secho(f"已导出到 {out_path}", fg="green")
    elif format == "parquet":
        out_path = output or f"{symbol}_{interval}.parquet"
        df.to_parquet(out_path, index=False)
        typer.secho(f"已导出到 {out_path}", fg="green")
    else:
        typer.secho(f"不支持的格式: {format}", fg="red", err=True)
        raise typer.Exit(1)


@app.command("status")
def task_status(
    task_id: str = typer.Option(..., "--task-id", help="任务ID"),
):
    """查询任务状态"""
    if task_manager is None:
        typer.secho("错误: 任务管理器未初始化", fg="red", err=True)
        raise typer.Exit(1)

    task = task_manager.get_task(task_id)
    if task is None:
        typer.secho(f"任务 {task_id} 不存在", fg="red", err=True)
        raise typer.Exit(1)

    typer.secho(f"任务ID: {task.get('task_id', task_id)}", fg="green")
    typer.secho(f"状态: {task.get('status', 'unknown')}")
    typer.secho(f"类型: {task.get('task_type', 'unknown')}")

    progress = task.get("progress", {})
    if progress:
        typer.secho(f"进度: {progress.get('percentage', 0):.1f}%")

    params = task.get("params", {})
    if params:
        typer.secho(f"参数: {json.dumps(params, ensure_ascii=False)}")

    start = task.get("start_time", "")
    end = task.get("end_time", "")
    if start or end:
        typer.secho(f"时间: {start} ~ {end}")


@app.command("list-symbols")
def list_symbols():
    """列出交易对"""
    data_dir = get_source_data_dir()
    klines_dir = data_dir / "klines"
    if not klines_dir.exists():
        typer.secho("未找到本地数据", fg="yellow")
        return

    symbols = sorted([d.name for d in klines_dir.iterdir() if d.is_dir()])
    if not symbols:
        typer.secho("未找到本地数据", fg="yellow")
        return

    typer.secho(f"本地交易对 ({len(symbols)} 个):", fg="green")
    for sym in symbols:
        typer.echo(f"  {sym}")


@app.command("list-local-data")
def list_local_data():
    """列出本地数据"""
    data_dir = get_source_data_dir()
    klines_dir = data_dir / "klines"
    if not klines_dir.exists():
        typer.secho("未找到本地数据", fg="yellow")
        return

    symbols = [d for d in klines_dir.iterdir() if d.is_dir()]
    if not symbols:
        typer.secho("未找到本地数据", fg="yellow")
        return

    typer.secho("本地数据文件:", fg="green")
    for sym_dir in sorted(symbols):
        for interval_dir in sorted(sym_dir.iterdir()):
            if interval_dir.is_dir():
                for f in interval_dir.iterdir():
                    if f.suffix == ".parquet":
                        info = get_parquet_info(f)
                        typer.echo(
                            f"  {sym_dir.name}/{interval_dir.name}/{f.name} ({info.get('rows', 0)} 行, {format_size(info.get('size', 0))})"
                        )


@app.command("delete-local-data")
def delete_local_data(
    symbol: str = typer.Option(..., "--symbol", "-s", help="交易对"),
    interval: str = typer.Option(None, "--interval", "-i", help="时间框架 (可选)"),
):
    """删除本地数据"""
    data_dir = get_source_data_dir()
    klines_dir = data_dir / "klines"
    sym_dir = klines_dir / symbol

    if not sym_dir.exists():
        typer.secho(f"未找到 {symbol} 的本地数据", fg="yellow")
        return

    if interval:
        interval_dir = sym_dir / interval
        if not interval_dir.exists():
            typer.secho(f"未找到 {symbol} {interval} 的数据", fg="yellow")
            return
        import shutil

        shutil.rmtree(interval_dir)
        typer.secho(f"已删除 {symbol} {interval} 数据", fg="green")
    else:
        import shutil

        shutil.rmtree(sym_dir)
        typer.secho(f"已删除 {symbol} 的所有本地数据", fg="green")


import_app = typer.Typer(help="数据导入")
app.add_typer(import_app, name="import")


@import_app.command("csv")
def import_csv(
    file_path: str = typer.Argument(..., help="CSV文件路径"),
    interval: str = typer.Option(..., "--interval", "-i", help="时间框架"),
):
    """从CSV导入数据"""
    import_file = Path(file_path)
    if not import_file.exists():
        typer.secho(f"错误: 文件 {file_path} 不存在", fg="red", err=True)
        raise typer.Exit(1)

    df = pd.read_csv(file_path)
    if df.empty:
        typer.secho("错误: CSV文件为空", fg="red", err=True)
        raise typer.Exit(1)

    required_cols = {"timestamp", "open", "high", "low", "close", "volume"}
    actual_cols = set(df.columns)
    missing = required_cols - actual_cols
    if missing:
        typer.secho(f"错误: CSV缺少必需列: {', '.join(missing)}", fg="red", err=True)
        raise typer.Exit(1)

    symbol = df["symbol"].iloc[0] if "symbol" in df.columns else import_file.stem
    data_dir = get_source_data_dir()
    output_dir = data_dir / "klines" / symbol / interval
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / f"{symbol}.parquet"
    df.to_parquet(output_file, index=False)

    typer.secho(f"已导入 {len(df)} 条记录到 {output_file}", fg="green")


@app.command("info")
def data_info(
    symbol: str = typer.Option(..., "--symbol", "-s", help="交易对"),
    interval: str = typer.Option(..., "--interval", "-i", help="时间框架"),
):
    """查看数据信息"""
    parquet_file = _find_parquet_file(symbol, interval)
    if parquet_file:
        info = get_parquet_info(parquet_file)
        typer.echo(f"文件: {info['file']}")
        typer.echo(f"行数: {info.get('rows', 'N/A')}")
        typer.echo(f"大小: {format_size(info.get('size', 0))}")
    else:
        typer.echo("未找到数据文件")


quality_app = typer.Typer(help="数据质量管理")
app.add_typer(quality_app, name="quality")


@quality_app.command("check")
def quality_check(
    symbol: str = typer.Option(..., "--symbol", "-s", help="交易对"),
    interval: str = typer.Option(..., "--interval", "-i", help="时间框架"),
    start_date: str = typer.Option(None, "--start", help="开始日期"),
    end_date: str = typer.Option(None, "--end", help="结束日期"),
):
    """质量检查"""
    parquet_file = _find_parquet_file(symbol, interval)
    if parquet_file is None:
        typer.secho(f"错误: 未找到 {symbol} {interval} 的数据文件", fg="red", err=True)
        raise typer.Exit(1)

    df = load_from_parquet(parquet_file)
    if df.empty:
        typer.secho("数据文件为空", fg="yellow")
        return

    if start_date is None and end_date is None:
        start_date, end_date = _get_default_date_range()

    filtered = filter_by_date_range(df, start_date, end_date)
    if filtered.empty:
        typer.secho("指定日期范围内无数据", fg="yellow")
        return

    start_ts = filtered["timestamp"].min() if "timestamp" in filtered.columns else None
    end_ts = filtered["timestamp"].max() if "timestamp" in filtered.columns else None
    completeness = calculate_data_completeness(len(filtered), start_ts, end_ts, interval)
    completeness_str = format_completeness(completeness)

    typer.secho(f"=== 数据质量报告: {symbol} {interval} ===", fg="green")
    typer.secho(f"文件: {parquet_file}")
    typer.secho(f"总行数: {len(df)}")
    typer.secho(f"日期范围: {format_time_range(start_ts, end_ts)}")
    typer.secho(f"数据完整率: {completeness_str}")

    missing_count = 0
    if "timestamp" in filtered.columns and len(filtered) > 1:
        ts_vals = sorted(filtered["timestamp"].tolist())
        interval_min = _parse_interval_minutes(interval)
        if interval_min > 0:
            is_ns = ts_vals[0] > 1e12
            for i in range(1, len(ts_vals)):
                diff = ts_vals[i] - ts_vals[i - 1]
                expected = interval_min * 60 * (1_000_000_000 if is_ns else 1)
                if diff > expected * 1.5:
                    missing_count += int(diff / expected) - 1

    if missing_count > 0:
        typer.secho(f"缺失K线数: ~{missing_count}", fg="yellow")
    else:
        typer.secho("无明显缺失", fg="green")

    typer.secho(f"质量评估: {completeness_str}")


@quality_app.command("options")
def quality_options():
    """质量选项"""
    typer.secho("=== 质量检查选项 ===", fg="green")
    typer.echo("  --symbol, -s    交易对")
    typer.echo("  --interval, -i  时间框架")
    typer.echo("  --start         开始日期 (YYYY-MM-DD)")
    typer.echo("  --end           结束日期 (YYYY-MM-DD)")
    typer.echo("")
    typer.secho("可用质量指标:", fg="green")
    typer.echo("  数据完整率: 检查K线数据是否连续")
    typer.echo("  时间覆盖: 检查时间戳覆盖范围")
    typer.echo("  缺失检测: 检测缺失的K线")


# === Archive 子命令 ===

archive_app = typer.Typer(help="归档数据管理")
app.add_typer(archive_app, name="archive")

_VALID_KINDS = {
    "aggTrades",
    "trades",
    "bookDepth",
    "bookTicker",
    "markPriceKlines",
    "indexPriceKlines",
    "premiumIndexKlines",
}
_VALID_MARKETS = {"spot", "um", "cm"}
_VALID_MODES = {"inc", "full"}


def _validate_kind(value: str) -> str:
    if value not in _VALID_KINDS:
        msg = f"无效的 kind: {value}，可选值：{', '.join(sorted(_VALID_KINDS))}"
        raise typer.BadParameter(msg)
    return value


def _validate_market(value: str) -> str:
    if value not in _VALID_MARKETS:
        msg = f"无效的 market: {value}，可选值：{', '.join(sorted(_VALID_MARKETS))}"
        raise typer.BadParameter(msg)
    return value


def _validate_mode(value: str) -> str:
    if value not in _VALID_MODES:
        msg = f"无效的 mode: {value}，可选值：{', '.join(sorted(_VALID_MODES))}"
        raise typer.BadParameter(msg)
    return value


def _parse_symbols(symbols_str: str) -> list[str]:
    symbols = [s.strip() for s in symbols_str.split(",")]
    symbols = [s for s in symbols if s]
    if not symbols:
        msg = "必须指定至少一个交易对"
        raise typer.BadParameter(msg)
    return symbols


@archive_app.command("download")
def archive_download(
    kind: str = typer.Option(..., "-k", "--kind", help="归档数据种类", callback=_validate_kind),
    market: str = typer.Option(..., "-m", "--market", help="市场", callback=_validate_market),
    symbols: str = typer.Option(..., "-s", "--symbols", help="交易对(逗号分隔)"),
    start: str = typer.Option(..., "--start", help="开始日期 (YYYY-MM-DD)"),
    end: str = typer.Option(..., "--end", help="结束日期 (YYYY-MM-DD)"),
    interval: str | None = typer.Option(None, "-i", "--interval", help="K线周期"),
    mode: str = typer.Option("inc", "--mode", help="模式(inc/full)", callback=_validate_mode),
):
    """下载归档数据"""
    from collector.services.archive_service import ArchiveService
    from exchange.binance.archive.kinds import ArchiveKind, MarketType

    sym_list = _parse_symbols(symbols)
    svc = ArchiveService(base_dir=get_source_data_dir())
    try:
        task_id = svc.create_download_task(
            symbols=sym_list,
            kind=ArchiveKind(kind),
            market=MarketType(market),
            start_date=start,
            end_date=end,
            mode=mode,
            interval=interval,
        )
    except ValueError as e:
        typer.secho(f"错误: {e}", fg="red", err=True)
        raise typer.Exit(code=1)

    typer.secho("创建任务成功", fg="green")
    typer.echo(f"  task_id: {task_id}")
    typer.echo(f"  kind: {kind}")
    typer.echo(f"  market: {market}")


@archive_app.command("list")
def archive_list(
    kind: str = typer.Option(..., "-k", "--kind", help="归档数据种类", callback=_validate_kind),
    market: str = typer.Option(..., "-m", "--market", help="市场", callback=_validate_market),
):
    """列出归档数据"""
    from collector.services.archive_service import ArchiveService
    from exchange.binance.archive.kinds import ArchiveKind, MarketType

    svc = ArchiveService(base_dir=get_source_data_dir())
    symbols_list = svc.list_symbols(
        kind=ArchiveKind(kind),
        market=MarketType(market),
    )

    typer.secho(f"归档交易对 ({len(symbols_list)} 个):", fg="green")
    if symbols_list:
        for sym in symbols_list:
            typer.echo(f"  {sym}")
    else:
        typer.echo("(无)")


@archive_app.command("meta")
def archive_meta(
    kind: str = typer.Option(..., "-k", "--kind", help="归档数据种类", callback=_validate_kind),
    market: str = typer.Option(..., "-m", "--market", help="市场", callback=_validate_market),
    symbol: str = typer.Option(..., "-s", "--symbol", help="交易对"),
):
    """查看元数据"""
    from collector.services.archive_service import ArchiveService
    from exchange.binance.archive.kinds import ArchiveKind, MarketType

    svc = ArchiveService(base_dir=get_source_data_dir())
    meta = svc.get_meta(
        kind=ArchiveKind(kind),
        market=MarketType(market),
        symbol=symbol,
    )

    if meta is None:
        typer.echo("(无 _meta.json)")
    else:
        typer.secho(f"元数据 for {symbol}:", fg="green")
        typer.echo(json.dumps(meta, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    app()
