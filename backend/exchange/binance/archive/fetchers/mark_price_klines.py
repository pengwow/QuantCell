"""markPriceKlines 标记价 K 线下载器（Task 9 完整实现）。

markPriceKlines zip 内的 CSV 来自 Binance 合约历史归档, 列顺序固定为
`(open_time, open, high, low, close, volume, ignore, close_time, quote_volume,
count, ...)`。其中 `ignore` 和 `close_time` 是冗余列, 必须在 transform_df
中丢弃, 只保留 8 列标准 schema (spec §3.2 markPriceKlines).
"""
from __future__ import annotations

import pyarrow as pa

from exchange.binance.archive.base import BaseBinanceArchiveDownloader
from exchange.binance.archive.kinds import ArchiveKind


# 标准 pyarrow schema: 8 列 (spec §3.2 markPriceKlines)
MARK_KLINES_SCHEMA = pa.schema([
    pa.field('open_time', pa.int64()),  # 毫秒
    pa.field('open', pa.float64()),
    pa.field('high', pa.float64()),
    pa.field('low', pa.float64()),
    pa.field('close', pa.float64()),
    pa.field('volume', pa.float64()),
    pa.field('quote_volume', pa.float64()),
    pa.field('count', pa.int32()),
])


class MarkPriceKlinesFetcher(BaseBinanceArchiveDownloader):
    """标记价 K 线（Mark Price Klines）下载器。

    URL 与文件名带 interval 段 (e.g. `markPriceKlines-1h-2024-12-01.zip`),
    由基类 `get_zip_url` 拼装; 子类只声明 interval 依赖。
    """

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
    parquet_schema = MARK_KLINES_SCHEMA
