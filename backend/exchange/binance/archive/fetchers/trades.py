"""trades 逐笔成交下载器（Task 6 完整实现）。

trades zip 内的 CSV **不带 header**, 列顺序固定为
(id, price, qty, quote_qty, time, is_buyer_maker), 因此子类重写
`_parse_csv_bytes` 强制指定列名, 而 `transform_df` 沿用基类 passthrough
行为即可。
"""

from __future__ import annotations

import io

import pandas as pd
import pyarrow as pa

from exchange.binance.archive.base import BaseBinanceArchiveDownloader
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
        """trades zip 内的 CSV 无 header, 强制指定列名.

        `Binance 官方逐笔成交` CSV 列顺序固定, 用 `names=` 锁定, 避免
        pandas 把首行数据当作列名.
        """
        return pd.read_csv(io.BytesIO(data), header=None, names=_TRADES_COLS)
