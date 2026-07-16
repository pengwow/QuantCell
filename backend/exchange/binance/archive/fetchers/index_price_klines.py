"""indexPriceKlines 指数价 K 线下载器（Task 10 完整实现）。

与 markPriceKlines 同源 (8 个 K 线列), 多 1 列 `index_price` (f64) 记录
Binance 指数价 (spec §3.2 indexPriceKlines).
"""
from __future__ import annotations

import pyarrow as pa

from exchange.binance.archive.base import BaseBinanceArchiveDownloader
from exchange.binance.archive.kinds import ArchiveKind


# 标准 pyarrow schema: 9 列 (8 K 线列 + index_price f64)
INDEX_KLINES_SCHEMA = pa.schema([
    pa.field('open_time', pa.int64()),  # 毫秒
    pa.field('open', pa.float64()),
    pa.field('high', pa.float64()),
    pa.field('low', pa.float64()),
    pa.field('close', pa.float64()),
    pa.field('volume', pa.float64()),
    pa.field('quote_volume', pa.float64()),
    pa.field('count', pa.int32()),
    pa.field('index_price', pa.float64()),
])


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
    parquet_schema = INDEX_KLINES_SCHEMA
