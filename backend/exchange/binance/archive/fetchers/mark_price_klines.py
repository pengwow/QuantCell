"""markPriceKlines 标记价 K 线下载器（Task 9 完整实现；本 task 提供最小桩）。"""
from __future__ import annotations

from exchange.binance.archive.base import BaseBinanceArchiveDownloader
from exchange.binance.archive.kinds import ArchiveKind


class MarkPriceKlinesFetcher(BaseBinanceArchiveDownloader):
    """标记价 K 线（Mark Price Klines）下载器。"""

    archive_kind = ArchiveKind.MARK_KLINES
    url_subpath = 'markPriceKlines'
    column_mapping = {
        'open_time': 'open_time',
        'open': 'open',
        'high': 'high',
        'low': 'low',
        'close': 'close',
        'volume': 'volume',
        'quote_volume': 'quote_volume',
        'count': 'count',
    }
    parquet_schema = None
