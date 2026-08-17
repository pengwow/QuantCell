"""premiumIndexKlines 溢价指数 K 线下载器（Task 11 完整实现）。

与 markPriceKlines 同源 (8 个 K 线列), 多 1 列 `premium_index` (f64) 记录
Binance 溢价指数 (mark price - index price) / index price, spec §3.2
premiumIndexKlines.
"""
from __future__ import annotations

import pyarrow as pa

from exchange.binance.archive.base import BaseBinanceArchiveDownloader
from exchange.binance.archive.kinds import ArchiveKind


# 标准 pyarrow schema: 9 列 (8 K 线列 + premium_index f64)
PREMIUM_KLINES_SCHEMA = pa.schema([
    pa.field('open_time', pa.int64()),  # 毫秒
    pa.field('open', pa.float64()),
    pa.field('high', pa.float64()),
    pa.field('low', pa.float64()),
    pa.field('close', pa.float64()),
    pa.field('volume', pa.float64()),
    pa.field('quote_volume', pa.float64()),
    pa.field('count', pa.int32()),
    pa.field('premium_index', pa.float64()),
])


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
    parquet_schema = PREMIUM_KLINES_SCHEMA
