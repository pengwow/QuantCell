"""bookDepth 深度快照下载器（Task 7 完整实现；本 task 提供最小桩）。"""
from __future__ import annotations

from exchange.binance.archive.base import BaseBinanceArchiveDownloader
from exchange.binance.archive.kinds import ArchiveKind


class BookDepthFetcher(BaseBinanceArchiveDownloader):
    """深度快照（Book Depth）下载器。"""

    archive_kind = ArchiveKind.BOOK_DEPTH
    url_subpath = 'bookDepth'
    # bookDepth zip 内是每 100ms / 1000ms 的部分深度快照；列在 Task 7 完整实现中定义
    column_mapping = {}
    parquet_schema = None
