"""aggTrades 聚合成交下载器。

aggTrades zip 内的 CSV **不带 header**, 列顺序固定为
(agg_trade_id, price, quantity, first_trade_id, last_trade_id, transact_time, is_buyer_maker),
因此子类重写 `_parse_csv_bytes` 强制指定列名。
"""

from __future__ import annotations

import io

import pandas as pd
import pyarrow as pa

from exchange.binance.archive.base import BaseBinanceArchiveDownloader
from exchange.binance.archive.kinds import ArchiveKind

# 标准 pyarrow schema: 7 列, i64/f64/bool
AGG_TRADES_SCHEMA = pa.schema(
    [
        pa.field("agg_trade_id", pa.int64()),
        pa.field("price", pa.float64()),
        pa.field("quantity", pa.float64()),
        pa.field("first_trade_id", pa.int64()),
        pa.field("last_trade_id", pa.int64()),
        pa.field("transact_time", pa.int64()),
        pa.field("is_buyer_maker", pa.bool_()),
    ]
)

# Binance aggTrades zip 内的 CSV 列顺序 (无 header)
_AGG_TRADES_COLS = [
    "agg_trade_id",
    "price",
    "quantity",
    "first_trade_id",
    "last_trade_id",
    "transact_time",
    "is_buyer_maker",
]


class AggTradesFetcher(BaseBinanceArchiveDownloader):
    """聚合成交（Agg Trades）下载器。"""

    archive_kind = ArchiveKind.AGG_TRADES
    url_subpath = "aggTrades"
    column_mapping = {col: col for col in _AGG_TRADES_COLS}
    parquet_schema = AGG_TRADES_SCHEMA

    def _parse_csv_bytes(self, data: bytes) -> pd.DataFrame:
        """aggTrades zip 内的 CSV 无 header, 强制指定列名。"""
        return pd.read_csv(
            io.BytesIO(data),
            header=None,
            names=_AGG_TRADES_COLS,
            usecols=range(len(_AGG_TRADES_COLS)),
        )

    def transform_df(self, raw_df: pd.DataFrame) -> pd.DataFrame:
        """强制列类型, 确保 parquet schema 一致。"""
        return raw_df.assign(
            agg_trade_id=raw_df["agg_trade_id"].astype("int64"),
            price=raw_df["price"].astype("float64"),
            quantity=raw_df["quantity"].astype("float64"),
            first_trade_id=raw_df["first_trade_id"].astype("int64"),
            last_trade_id=raw_df["last_trade_id"].astype("int64"),
            transact_time=raw_df["transact_time"].astype("int64"),
            is_buyer_maker=raw_df["is_buyer_maker"].astype("bool"),
        )
