"""trades 逐笔成交下载器（Task 6 完整实现；本 task 提供最小桩）。"""
from __future__ import annotations

from exchange.binance.archive.base import BaseBinanceArchiveDownloader
from exchange.binance.archive.kinds import ArchiveKind


class TradesFetcher(BaseBinanceArchiveDownloader):
    """逐笔成交（Trades）下载器。"""

    archive_kind = ArchiveKind.TRADES
    url_subpath = 'trades'
    column_mapping = {
        'id': 'id',
        'price': 'price',
        'qty': 'qty',
        'quote_qty': 'quote_qty',
        'time': 'time',
        'is_buyer_maker': 'is_buyer_maker',
    }
    parquet_schema = None
