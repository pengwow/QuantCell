"""aggTrades 聚合成交下载器（Task 5 完整实现；本 task 提供最小桩）。"""
from __future__ import annotations

from exchange.binance.archive.base import BaseBinanceArchiveDownloader
from exchange.binance.archive.kinds import ArchiveKind


class AggTradesFetcher(BaseBinanceArchiveDownloader):
    """聚合成交（Agg Trades）下载器。"""

    archive_kind = ArchiveKind.AGG_TRADES
    # Binance 官方 zip 路径片段（与 ArchiveKind 值一致）
    url_subpath = 'aggTrades'
    # 原始列名 → 标准化列名映射
    column_mapping = {
        'agg_trade_id': 'agg_trade_id',
        'price': 'price',
        'quantity': 'quantity',
        'first_trade_id': 'first_trade_id',
        'last_trade_id': 'last_trade_id',
        'transact_time': 'transact_time',
        'is_buyer_maker': 'is_buyer_maker',
    }
    # None 表示由 pandas/pyarrow 自动推断 schema
    parquet_schema = None
