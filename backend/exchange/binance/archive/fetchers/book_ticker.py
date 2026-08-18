"""bookTicker 最优挂单下载器（Task 7 完整实现）。

bookTicker zip 内通常 **没有时间戳列** (只有 update_id / symbol / 4 个
bid/ask 列), 需要子类在 `transform_df` 注入 `timestamp` (Unix 毫秒),
后续 `save_instrument` 走基类逻辑 (按 BOOK_TICKER_SCHEMA 写入 7 列含
timestamp).
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import pyarrow as pa

from exchange.binance.archive.base import BaseBinanceArchiveDownloader
from exchange.binance.archive.kinds import ArchiveKind

if TYPE_CHECKING:
    import pandas as pd

# 标准 pyarrow schema: 7 列, 含注入的 timestamp (i64) + 4 个 bid/ask (f64) + symbol (string)
BOOK_TICKER_SCHEMA = pa.schema(
    [
        pa.field("update_id", pa.int64()),
        pa.field("timestamp", pa.int64()),  # 由 transform_df 注入 (Unix 毫秒)
        pa.field("symbol", pa.string()),
        pa.field("best_bid_price", pa.float64()),
        pa.field("best_bid_qty", pa.float64()),
        pa.field("best_ask_price", pa.float64()),
        pa.field("best_ask_qty", pa.float64()),
    ]
)


class BookTickerFetcher(BaseBinanceArchiveDownloader):
    """最优挂单（Book Ticker）下载器。"""

    archive_kind = ArchiveKind.BOOK_TICKER
    url_subpath = "bookTicker"
    # column_mapping 只列 6 个 raw → standard 映射; timestamp 是注入列, 不在 raw 中
    column_mapping = {
        "update_id": "update_id",
        "symbol": "symbol",
        "best_bid_price": "best_bid_price",
        "best_bid_qty": "best_bid_qty",
        "best_ask_price": "best_ask_price",
        "best_ask_qty": "best_ask_qty",
    }
    parquet_schema = BOOK_TICKER_SCHEMA

    def transform_df(self, raw_df: pd.DataFrame) -> pd.DataFrame:
        """bookTicker zip 内可能没有 timestamp 列; 缺则注入当前 Unix 毫秒.

        ponytail: 取注入时间精度为秒级 (整毫秒), 在秒级时间分辨需求下足够; 若
        未来需要更高精度 (例如秒内多次采样), 升级为 `time.time_ns() // 1_000_000`.
        """
        if "timestamp" in raw_df.columns:
            return raw_df
        ts_ms = int(time.time() * 1000)
        return raw_df.assign(timestamp=ts_ms)
