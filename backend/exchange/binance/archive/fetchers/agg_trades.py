"""aggTrades 聚合成交下载器（Task 5 完整实现）。

aggTrades zip 内的 CSV **带 header**, 列名已经是 snake_case, 因此
`column_mapping` 是 identity (原始列名 = 标准列名), `transform_df` 只负责
强制列类型 (避免 pandas 推断为 object/nullable), 让最终 parquet schema 落
到 AGG_TRADES_SCHEMA。
"""
from __future__ import annotations

import pandas as pd
import pyarrow as pa

from exchange.binance.archive.base import BaseBinanceArchiveDownloader
from exchange.binance.archive.kinds import ArchiveKind


# 标准 pyarrow schema: 7 列, i64/f64/bool
AGG_TRADES_SCHEMA = pa.schema([
    pa.field('agg_trade_id', pa.int64()),
    pa.field('price', pa.float64()),
    pa.field('quantity', pa.float64()),
    pa.field('first_trade_id', pa.int64()),
    pa.field('last_trade_id', pa.int64()),
    pa.field('transact_time', pa.int64()),  # 毫秒
    pa.field('is_buyer_maker', pa.bool_()),
])


class AggTradesFetcher(BaseBinanceArchiveDownloader):
    """聚合成交（Agg Trades）下载器。"""

    archive_kind = ArchiveKind.AGG_TRADES
    # Binance 官方 zip 路径片段（与 ArchiveKind 值一致）
    url_subpath = 'aggTrades'
    # 原始列名 → 标准化列名映射 (identity)
    column_mapping = {
        'agg_trade_id': 'agg_trade_id',
        'price': 'price',
        'quantity': 'quantity',
        'first_trade_id': 'first_trade_id',
        'last_trade_id': 'last_trade_id',
        'transact_time': 'transact_time',
        'is_buyer_maker': 'is_buyer_maker',
    }
    parquet_schema = AGG_TRADES_SCHEMA

    def transform_df(self, raw_df: pd.DataFrame) -> pd.DataFrame:
        """aggTrades zip 内的 CSV 带 header, 列名已是 snake_case.

        强制 7 列类型, 避免 pandas 推断为 object / nullable boolean (后者读回
        parquet 后会变成 'boolean' 而非 'bool', 不利于下游统一处理).
        """
        return raw_df.assign(
            agg_trade_id=raw_df['agg_trade_id'].astype('int64'),
            price=raw_df['price'].astype('float64'),
            quantity=raw_df['quantity'].astype('float64'),
            first_trade_id=raw_df['first_trade_id'].astype('int64'),
            last_trade_id=raw_df['last_trade_id'].astype('int64'),
            transact_time=raw_df['transact_time'].astype('int64'),
            is_buyer_maker=raw_df['is_buyer_maker'].astype('bool'),
        )
