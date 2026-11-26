"""K 线数据的本地 parquet 浏览（「归档检索」卡里 kind=kline 的分支）。

归档服务（archive_service）只服务 Binance Vision 的 7 种归档 zip；K 线数据落的是
本地 parquet（回测 / 研究 / 因子读的是同一份文件），所以这里单独读盘，返回形状与
archive_service 对齐（symbols / {total, rows, truncated} / meta），前端不必分叉。

market 口径：归档枚举是 spot / um / cm，K 线目录只有 spot / future，
所以除 spot 外一律读 future（um 与 cm 共用同一份合约 K 线）。

ponytail: interval 缺省取该 symbol 的第一个可用周期（与归档 fetcher 的「按 symbol
自适应」同口径）；页面显式传周期时以页面为准。落盘时间列单位不统一（现货微秒 / 合约毫秒），
出参一律按量级归一到毫秒，与归档行同单位。
"""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from quality.parquet_provider import ParquetDataProvider
from utils import normalize_symbol


def _to_ms(value: int) -> int:
    """落盘时间列单位不统一（现货为微秒、合约为毫秒），按量级归一到毫秒。"""
    while value > 10**14:
        value //= 1000
    return value


def _candle_type(market: str) -> str:
    return "spot" if market == "spot" else "future"


def _klines_root(provider: ParquetDataProvider, candle_type: str):
    # 不碰 provider 的私有方法：布局与 ParquetDataProvider 同约定
    return provider.base_dir / "crypto" / candle_type / "klines"


def _resolve_interval(
    provider: ParquetDataProvider,
    symbol: str,
    candle_type: str,
    interval: str | None,
) -> str | None:
    if interval:
        return interval
    for entry in provider.list_available_symbols(candle_type):
        if entry["symbol"] == normalize_symbol(symbol):
            intervals = entry.get("intervals") or []
            return intervals[0] if intervals else None
    return None


def list_symbols(market: str, interval: str | None = None) -> list[str]:
    """已下载 K 线的标的（文件名即 symbol，与 ParquetDataProvider 同口径）。"""
    entries = ParquetDataProvider().list_available_symbols(_candle_type(market), interval)
    return [entry["symbol"] for entry in entries]


def query_data(
    market: str,
    symbol: str,
    start_time: int,
    end_time: int,
    limit: int = 1000,
    offset: int = 0,
    interval: str | None = None,
) -> dict:
    """按毫秒窗口分页读取本地 K 线；形状与 archive_service.query_data 一致。"""
    provider = ParquetDataProvider()
    candle_type = _candle_type(market)
    resolved = _resolve_interval(provider, symbol, candle_type, interval)
    if not resolved:
        return {"total": 0, "rows": [], "truncated": False}

    start = pd.to_datetime(start_time, unit="ms").strftime("%Y-%m-%d %H:%M:%S")
    end = pd.to_datetime(end_time, unit="ms").strftime("%Y-%m-%d %H:%M:%S")
    try:
        df = provider.get_kline_data(symbol, resolved, candle_type, start, end)
    except FileNotFoundError:
        return {"total": 0, "rows": [], "truncated": False}

    total = len(df)
    rows: list[dict] = []
    for record in df.iloc[offset : offset + limit].to_dict("records"):
        for key in ("timestamp", "close_time"):
            value = record.get(key)
            if isinstance(value, int):
                record[key] = _to_ms(value)
        rows.append(record)
    return {"total": total, "rows": rows, "truncated": offset + limit < total}


def get_meta(market: str, symbol: str, interval: str | None = None) -> dict | None:
    """本地 parquet 的覆盖摘要（无 _meta.json，按文件与时间列现算）。"""
    provider = ParquetDataProvider()
    candle_type = _candle_type(market)
    resolved = _resolve_interval(provider, symbol, candle_type, interval)
    if not resolved:
        return None
    try:
        df = provider.get_kline_data(symbol, resolved, candle_type, columns=["timestamp"])
    except FileNotFoundError:
        return None
    if df.empty:
        return None

    stamps = df["timestamp"]
    earliest = pd.to_datetime(_to_ms(int(stamps.min())), unit="ms")
    latest = pd.to_datetime(_to_ms(int(stamps.max())), unit="ms")
    root = _klines_root(provider, candle_type)
    files = sorted(root.glob(f"*/{normalize_symbol(symbol)}.parquet"))
    updated = max((f.stat().st_mtime for f in files), default=None)
    return {
        "symbol": normalize_symbol(symbol),
        "kind": "kline",
        "market": market,
        "earliest_date": earliest.date().isoformat(),
        "latest_date": latest.date().isoformat(),
        "total_rows": len(df),
        "file_count": len(files),
        "corrupt_dates": [],
        "updated_at": (datetime.fromtimestamp(updated, tz=UTC).isoformat() if updated else ""),
    }


def delete_symbol(market: str, symbol: str, interval: str | None = None) -> str | None:
    """删除该 symbol 的本地 K 线文件（指定周期时只删那一个），返回已删路径。"""
    provider = ParquetDataProvider()
    root = _klines_root(provider, _candle_type(market))
    pattern = f"{interval}/{normalize_symbol(symbol)}.parquet" if interval else f"*/{normalize_symbol(symbol)}.parquet"
    targets = [path for path in root.glob(pattern) if path.is_file()]
    for path in targets:
        path.unlink()
    return ", ".join(str(path) for path in targets) if targets else None
