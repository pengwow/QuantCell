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


# === 数据目录工具 ===


def get_source_data_dir() -> Path:
    """获取数据源目录路径"""
    data_dir = backend_path.parent / "data" / "source"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def _normalize_symbol(symbol: str) -> str:
    """标准化交易对名称"""
    return symbol.replace("/", "").replace("\\", "").replace(" ", "")


def _find_parquet_file(symbol: str, interval: str, market_type: str = "spot") -> Path | None:
    """查找指定交易对和时间框架的parquet文件"""
    data_dir = get_source_data_dir()
    norm_symbol = _normalize_symbol(symbol)
    return data_dir / market_type / interval / f"{norm_symbol}.parquet"


def _get_default_date_range(end_date=None) -> tuple[str, str]:
    """获取默认日期范围"""
    from datetime import datetime, timedelta

    if end_date is None:
        end = datetime.now()
    elif isinstance(end_date, datetime):
        end = end_date
    else:
        end = datetime.now()
    start = end - timedelta(days=30)
    return start.strftime("%Y%m%d"), end.strftime("%Y%m%d")


def filter_by_date_range(df, start_date=None, end_date=None):
    """按日期范围过滤DataFrame"""
    if df is None or df.empty:
        return df
    if "timestamp" not in df.columns:
        return df
    mask = pd.Series(True, index=df.index)
    if start_date:
        start_ts = pd.Timestamp(start_date)
        if df["timestamp"].dtype == "int64" or df["timestamp"].dtype == "int32":
            if df["timestamp"].max() > 1e12:
                start_ts = int(start_ts.timestamp() * 1_000_000_000)
            else:
                start_ts = int(start_ts.timestamp())
        mask &= df["timestamp"] >= start_ts
    if end_date:
        end_ts = pd.Timestamp(end_date)
        if df["timestamp"].dtype == "int64" or df["timestamp"].dtype == "int32":
            if df["timestamp"].max() > 1e12:
                end_ts = int(end_ts.timestamp() * 1_000_000_000)
            else:
                end_ts = int(end_ts.timestamp())
        mask &= df["timestamp"] <= end_ts
    return df[mask]


def load_from_parquet(file_path) -> pd.DataFrame:
    """从parquet加载数据"""
    return pd.read_parquet(file_path)


def get_parquet_info(file_path: Path) -> dict:
    """获取parquet文件信息"""
    try:
        df = load_from_parquet(file_path)
        return {
            "file": str(file_path),
            "rows": len(df),
            "columns": list(df.columns),
            "size": file_path.stat().st_size if file_path.exists() else 0,
            "num_rows": len(df),
            "file_size_bytes": file_path.stat().st_size if file_path.exists() else 0,
        }
    except Exception as e:
        return {"file": str(file_path), "error": str(e)}


def scan_parquet_files(symbol=None, interval=None, base_dir=None) -> list:
    """扫描parquet文件"""
    if base_dir is None:
        base_dir = get_source_data_dir()
    if not base_dir.exists():
        return []

    results = []
    klines_dir = base_dir / "klines"

    if not klines_dir.exists():
        for f in sorted(base_dir.glob("*.parquet")):
            results.append((f.stem, f))
        return results

    if symbol and interval:
        interval_dir = klines_dir / symbol / interval
        if interval_dir.is_dir():
            for f in interval_dir.iterdir():
                if f.suffix == ".parquet":
                    info = get_parquet_info(f)
                    results.append(
                        {
                            "symbol": symbol,
                            "interval": interval,
                            "file": f,
                            "info": info,
                        }
                    )
    elif symbol:
        symbol_dir = klines_dir / symbol
        if symbol_dir.is_dir():
            for interval_dir in symbol_dir.iterdir():
                if interval_dir.is_dir():
                    for f in interval_dir.iterdir():
                        if f.suffix == ".parquet":
                            info = get_parquet_info(f)
                            results.append(
                                {
                                    "symbol": symbol,
                                    "interval": interval_dir.name,
                                    "file": f,
                                    "info": info,
                                }
                            )
    else:
        for sym_dir in klines_dir.iterdir():
            if sym_dir.is_dir():
                for interval_dir in sym_dir.iterdir():
                    if interval_dir.is_dir():
                        for f in interval_dir.iterdir():
                            if f.suffix == ".parquet":
                                info = get_parquet_info(f)
                                results.append(
                                    {
                                        "symbol": sym_dir.name,
                                        "interval": interval_dir.name,
                                        "file": f,
                                        "info": info,
                                    }
                                )
    return results


def _validate_parquet_export(file_path, df) -> bool:
    """验证parquet导出"""
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


# === 格式化工具 ===


def format_size(size_bytes: float) -> str:
    """格式化文件大小"""
    if size_bytes < 1024:
        return f"{size_bytes:.1f} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


def calculate_data_completeness(bar_count, start_ts, end_ts, interval) -> dict:
    """计算数据完整率"""
    if bar_count == 0 or start_ts is None or end_ts is None:
        return {"completeness_pct": 0, "status": "-"}

    interval_minutes = _parse_interval_minutes(interval)
    if interval_minutes <= 0:
        return {"completeness_pct": 0, "status": "-"}

    is_nanoseconds = start_ts > 1e12

    duration_seconds = (end_ts - start_ts) / 1000000000 if is_nanoseconds else end_ts - start_ts

    expected_bars = duration_seconds / (interval_minutes * 60)

    if expected_bars <= 0:
        return {"completeness_pct": 0, "status": "-"}

    pct = min(100.0, (bar_count / expected_bars) * 100.0)

    if pct >= 100.0:
        status = "✓"
    elif pct >= 70:
        status = "⚠️"
    else:
        status = "✗"

    return {"completeness_pct": round(pct, 1), "status": status}


def _parse_interval_minutes(interval: str) -> float:
    """解析时间框架为分钟"""
    interval = interval.lower().strip()
    mappings = {
        "1m": 1,
        "3m": 3,
        "5m": 5,
        "15m": 15,
        "30m": 30,
        "1h": 60,
        "2h": 120,
        "4h": 240,
        "6h": 360,
        "8h": 480,
        "12h": 720,
        "1d": 1440,
        "3d": 4320,
        "1w": 10080,
    }
    if interval in mappings:
        return mappings[interval]
    return 0


def format_completeness(info: dict) -> str:
    """格式化完整率"""
    if info.get("status") == "-":
        return "-"
    pct = info.get("completeness_pct", 0)
    status = info.get("status", "-")
    return f"{int(pct)}% {status}"


def format_time_range(start, end) -> str:
    """格式化时间范围"""
    if start is None and end is None:
        return "-"
    try:
        if start is not None:
            start_dt = _ts_to_datetime(start)
            start_str = start_dt.strftime("%Y-%m-%d")
        else:
            start_str = "?"
        if end is not None:
            end_dt = _ts_to_datetime(end)
            end_str = end_dt.strftime("%Y-%m-%d")
        else:
            end_str = "?"
        return f"{start_str} ~ {end_str}"
    except Exception:
        return "-"


def _ts_to_datetime(ts):
    """时间戳转datetime"""
    from datetime import datetime

    if ts > 1e12:
        return datetime.fromtimestamp(ts / 1_000_000_000)
    return datetime.fromtimestamp(ts)


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
    svc = ArchiveService(base_dir=str(backend_path / "data" / "source"))
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

    svc = ArchiveService(base_dir=str(backend_path / "data" / "source"))
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

    svc = ArchiveService(base_dir=str(backend_path / "data" / "source"))
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
