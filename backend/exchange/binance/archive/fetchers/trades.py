"""trades 逐笔成交下载器（Task 6 完整实现）。

trades zip 内的 CSV **不带 header**, 列顺序固定为
(id, price, qty, quote_qty, time, is_buyer_maker), 因此子类重写
`_parse_csv_bytes` 强制指定列名, 而 `transform_df` 沿用基类 passthrough
行为即可。
"""

from __future__ import annotations

import pandas as pd
import pyarrow as pa

from exchange.binance.archive.base import (
    BaseBinanceArchiveDownloader,
    read_csv_with_header_sniff,
)
from exchange.binance.archive.kinds import ArchiveKind

# 标准 pyarrow schema: 6 列, i64/f64/bool
TRADES_SCHEMA = pa.schema(
    [
        pa.field("id", pa.int64()),
        pa.field("price", pa.float64()),
        pa.field("qty", pa.float64()),
        pa.field("quote_qty", pa.float64()),
        pa.field("time", pa.int64()),  # 毫秒
        pa.field("is_buyer_maker", pa.bool_()),
    ]
)

# Binance trades zip 内的 CSV 列顺序 (无 header)
_TRADES_COLS = ["id", "price", "qty", "quote_qty", "time", "is_buyer_maker"]


class TradesFetcher(BaseBinanceArchiveDownloader):
    """逐笔成交（Trades）下载器。"""

    archive_kind = ArchiveKind.TRADES
    url_subpath = "trades"
    column_mapping = {
        "id": "id",
        "price": "price",
        "qty": "qty",
        "quote_qty": "quote_qty",
        "time": "time",
        "is_buyer_maker": "is_buyer_maker",
    }
    parquet_schema = TRADES_SCHEMA

    def _parse_csv_bytes(self, data: bytes) -> pd.DataFrame:
        """嗅探 header：现行 Binance CSV（futures 全量/spot 2020 后）带 header，
        旧格式无 header，统一由基类嗅探函数处理，避免 header 行混入数据炸类型。"""
        return read_csv_with_header_sniff(data, _TRADES_COLS)
