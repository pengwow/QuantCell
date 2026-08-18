"""Binance 历史归档枚举与 URL 拼装工具。"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path


# —— 7 种归档数据种类 ——
class ArchiveKind(StrEnum):
    AGG_TRADES = "aggTrades"
    TRADES = "trades"
    BOOK_DEPTH = "bookDepth"
    BOOK_TICKER = "bookTicker"
    MARK_KLINES = "markPriceKlines"
    INDEX_KLINES = "indexPriceKlines"
    PREMIUM_KLINES = "premiumIndexKlines"


# —— 3 个市场 ——
class MarketType(StrEnum):
    SPOT = "spot"
    FUTURES_UM = "um"
    FUTURES_CM = "cm"


# —— 市场到 Binance URL 路径前缀 ——
_MARKET_URL_PREFIX: dict[MarketType, str] = {
    MarketType.SPOT: "data/spot",
    MarketType.FUTURES_UM: "data/futures/um",
    MarketType.FUTURES_CM: "data/futures/cm",
}


# —— K 线类支持的 interval（spec §3.4）——
KIND_INTERVALS: dict[ArchiveKind, list[str] | None] = {
    ArchiveKind.AGG_TRADES: None,
    ArchiveKind.TRADES: None,
    ArchiveKind.BOOK_DEPTH: None,
    ArchiveKind.BOOK_TICKER: None,
    ArchiveKind.MARK_KLINES: ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "1d"],
    ArchiveKind.INDEX_KLINES: ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "1d"],
    ArchiveKind.PREMIUM_KLINES: ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "1d"],
}


def build_zip_url(
    market: MarketType,
    kind: ArchiveKind,
    symbol: str,
    date_str: str,
    interval: str | None = None,
) -> str:
    """拼装 Binance 官方归档 zip 的下载 URL。

    Examples:
        >>> build_zip_url(MarketType.SPOT, ArchiveKind.AGG_TRADES, 'BTCUSDT', '2024-12-01')
        'https://data.binance.vision/data/spot/daily/aggTrades/BTCUSDT/BTCUSDT-aggTrades-2024-12-01.zip'
        >>> build_zip_url(MarketType.FUTURES_UM, ArchiveKind.MARK_KLINES, 'BTCUSDT', '2024-12-01', '1h')
        'https://data.binance.vision/data/futures/um/daily/markPriceKlines/BTCUSDT/1h/BTCUSDT-markPriceKlines-1h-2024-12-01.zip'
    """
    prefix = _MARKET_URL_PREFIX[market]
    interval_segment = f"{interval}/" if interval else ""
    file_stem = f"{symbol}-{kind.value}-{interval + '-' if interval else ''}{date_str}.zip"
    return f"https://data.binance.vision/{prefix}/daily/{kind.value}/{symbol}/{interval_segment}{file_stem}"


def get_save_dir(
    base_dir: str | Path,
    market: MarketType,
    kind: ArchiveKind,
    symbol: str,
) -> Path:
    """返回某 (market, kind, symbol) 的本地存储目录。

    Example: '/tmp/qc/spot/aggTrades/BTCUSDT'
    """
    return Path(base_dir) / market.value / kind.value / symbol
