"""Binance 历史归档（Tick + K 线）下载体系。

支持 7 种归档数据 × 3 个市场 = 21 种组合:
    aggTrades / trades / bookDepth / bookTicker
    markPriceKlines / indexPriceKlines / premiumIndexKlines
    ×
    spot / futures/um / futures/cm

全部只入 Parquet 分区（spec §3.1），不建 SQL 表。
不碰 realtime 引擎。
不修改现有 K 线数据流。
"""

from exchange.binance.archive.kinds import (
    ArchiveKind,
    MarketType,
    build_zip_url,
    get_save_dir,
    KIND_INTERVALS,
)

__all__ = [
    "ArchiveKind",
    "MarketType",
    "build_zip_url",
    "get_save_dir",
    "KIND_INTERVALS",
]
