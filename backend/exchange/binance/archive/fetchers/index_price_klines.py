"""indexPriceKlines 指数价 K 线下载器（Task 10 完整实现；本 task 提供最小桩）。"""
from __future__ import annotations

from exchange.binance.archive.base import BaseBinanceArchiveDownloader
from exchange.binance.archive.kinds import ArchiveKind


class IndexPriceKlinesFetcher(BaseBinanceArchiveDownloader):
    """指数价 K 线（Index Price Klines）下载器。"""

    archive_kind = ArchiveKind.INDEX_KLINES
    url_subpath = 'indexPriceKlines'
    column_mapping = {
        'open_time': 'open_time',
        'open': 'open',
        'high': 'high',
        'low': 'low',
        'close': 'close',
        'volume': 'volume',
        'quote_volume': 'quote_volume',
        'count': 'count',
        'index_price': 'index_price',
    }
    parquet_schema = None
