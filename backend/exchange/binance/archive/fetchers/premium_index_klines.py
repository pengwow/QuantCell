"""premiumIndexKlines 溢价指数 K 线下载器（Task 11 完整实现；本 task 提供最小桩）。"""
from __future__ import annotations

from exchange.binance.archive.base import BaseBinanceArchiveDownloader
from exchange.binance.archive.kinds import ArchiveKind


class PremiumIndexKlinesFetcher(BaseBinanceArchiveDownloader):
    """溢价指数 K 线（Premium Index Klines）下载器。"""

    archive_kind = ArchiveKind.PREMIUM_KLINES
    url_subpath = 'premiumIndexKlines'
    column_mapping = {
        'open_time': 'open_time',
        'open': 'open',
        'high': 'high',
        'low': 'low',
        'close': 'close',
        'volume': 'volume',
        'quote_volume': 'quote_volume',
        'count': 'count',
        'premium_index': 'premium_index',
    }
    parquet_schema = None
