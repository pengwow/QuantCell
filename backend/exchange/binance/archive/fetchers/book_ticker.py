"""bookTicker 最优挂单下载器（Task 8 完整实现；本 task 提供最小桩）。"""
from __future__ import annotations

from exchange.binance.archive.base import BaseBinanceArchiveDownloader
from exchange.binance.archive.kinds import ArchiveKind


class BookTickerFetcher(BaseBinanceArchiveDownloader):
    """最优挂单（Book Ticker）下载器。"""

    archive_kind = ArchiveKind.BOOK_TICKER
    url_subpath = 'bookTicker'
    column_mapping = {
        'update_id': 'update_id',
        'symbol': 'symbol',
        'best_bid_price': 'best_bid_price',
        'best_bid_qty': 'best_bid_qty',
        'best_ask_price': 'best_ask_price',
        'best_ask_qty': 'best_ask_qty',
    }
    parquet_schema = None
