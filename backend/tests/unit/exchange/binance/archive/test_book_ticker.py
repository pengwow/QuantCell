"""Tests for BookTickerFetcher 完整实现。

覆盖:
- column_mapping 6 个原始→标准映射 (不含注入的 timestamp)
- parquet_schema 7 列含 timestamp, i64/f64/string 类型正确
- transform_df 在源 df 缺 timestamp 时注入 (Unix 毫秒)
- transform_df 已有 timestamp 时不覆盖
- 端到端: collect_data → parquet 落盘 → read_range
"""
from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pytest

from exchange.binance.archive.fetchers.book_ticker import BookTickerFetcher
from exchange.binance.archive.kinds import ArchiveKind, MarketType


# ---- 静态钩子 ----

def test_column_mapping_has_6_entries():
    """column_mapping 6 个原始→标准映射 (不含注入的 timestamp)."""
    f = BookTickerFetcher(market=MarketType.SPOT, base_dir='/tmp', symbol='BTCUSDT')
    assert f.column_mapping == {
        'update_id': 'update_id',
        'symbol': 'symbol',
        'best_bid_price': 'best_bid_price',
        'best_bid_qty': 'best_bid_qty',
        'best_ask_price': 'best_ask_price',
        'best_ask_qty': 'best_ask_qty',
    }


def test_parquet_schema_has_7_fields_with_timestamp():
    """parquet_schema 7 列含 timestamp (int64)."""
    f = BookTickerFetcher(market=MarketType.SPOT, base_dir='/tmp', symbol='BTCUSDT')
    schema = f.parquet_schema
    assert isinstance(schema, pa.Schema), f"expected pa.Schema, got {type(schema)}"
    names = [field.name for field in schema]
    for col in (
        'update_id', 'timestamp', 'symbol',
        'best_bid_price', 'best_bid_qty',
        'best_ask_price', 'best_ask_qty',
    ):
        assert col in names, f"missing column in schema: {col}"
    types = {field.name: str(field.type) for field in schema}
    # i64: update_id, timestamp
    assert 'int64' in types['update_id']
    assert 'int64' in types['timestamp']
    # string: symbol
    assert 'string' in types['symbol']
    # f64: 4 个价格/数量列
    for col in ('best_bid_price', 'best_bid_qty', 'best_ask_price', 'best_ask_qty'):
        assert 'double' in types[col], f"{col} should be double, got {types[col]}"


# ---- transform_df 注入 timestamp ----

def test_transform_df_injects_timestamp_when_missing():
    """源 df 缺 timestamp 时, transform_df 必须注入当前 Unix 毫秒."""
    f = BookTickerFetcher(market=MarketType.SPOT, base_dir='/tmp', symbol='BTCUSDT')
    before_ms = int(time.time() * 1000)
    raw = pd.DataFrame({
        'update_id': [1, 2],
        'symbol': ['BTCUSDT', 'BTCUSDT'],
        'best_bid_price': [100.0, 101.0],
        'best_bid_qty': [1.0, 2.0],
        'best_ask_price': [101.0, 102.0],
        'best_ask_qty': [1.5, 2.5],
    })
    out = f.transform_df(raw)
    after_ms = int(time.time() * 1000)
    assert 'timestamp' in out.columns
    # 所有行的 timestamp 都在 [before_ms, after_ms] 区间
    for ts in out['timestamp']:
        assert before_ms <= int(ts) <= after_ms + 1000, (
            f"timestamp {ts} not in [{before_ms}, {after_ms}]"
        )
    # 其他列原样保留
    assert out['update_id'].tolist() == [1, 2]
    assert out['best_bid_price'].tolist() == [100.0, 101.0]


def test_transform_df_preserves_existing_timestamp():
    """源 df 已有 timestamp 时, transform_df 不覆盖."""
    f = BookTickerFetcher(market=MarketType.SPOT, base_dir='/tmp', symbol='BTCUSDT')
    raw = pd.DataFrame({
        'update_id': [1, 2],
        'symbol': ['BTCUSDT', 'BTCUSDT'],
        'best_bid_price': [100.0, 101.0],
        'best_bid_qty': [1.0, 2.0],
        'best_ask_price': [101.0, 102.0],
        'best_ask_qty': [1.5, 2.5],
        'timestamp': [1700000000000, 1700000000001],
    })
    out = f.transform_df(raw)
    assert out['timestamp'].tolist() == [1700000000000, 1700000000001]


# ---- 端到端 ----

def test_collect_data_writes_parquet_with_schema(monkeypatch, tmp_path: Path):
    """collect_data 写出的 parquet 必须含 timestamp 列, 符合 schema.

    注: monkeypatch 掉了 _run_async, 等价于模拟 transform_df 已注入 timestamp
    后的 df 直接送 save_instrument. transform_df 注入逻辑见上面的
    test_transform_df_injects_timestamp_when_missing.
    """
    f = BookTickerFetcher(
        market=MarketType.SPOT, base_dir=tmp_path, symbol='BTCUSDT', interval=None,
    )
    sample_df = pd.DataFrame({
        'update_id': [1, 2, 3],
        'symbol': ['BTCUSDT', 'BTCUSDT', 'BTCUSDT'],
        'best_bid_price': [100.0, 101.0, 102.0],
        'best_bid_qty': [1.0, 2.0, 3.0],
        'best_ask_price': [101.0, 102.0, 103.0],
        'best_ask_qty': [1.5, 2.5, 3.5],
        'timestamp': [1700000000000, 1700000000001, 1700000000002],
    })

    def fake_run_async(self, coro_func, *args):
        return sample_df

    monkeypatch.setattr(BookTickerFetcher, '_run_async', fake_run_async)
    result = f.collect_data(symbols=['BTCUSDT'], start='2024-12-01', end='2024-12-01', mode='inc')
    assert result['files_added'] == 1
    assert result['symbols_processed'] == 1

    out_path = f.save_dir / 'BTCUSDT-bookTicker-2024-12-01.parquet'
    assert out_path.exists()

    loaded = pd.read_parquet(out_path)
    assert len(loaded) == 3
    # timestamp 列存在且为 int64
    assert 'timestamp' in loaded.columns
    assert loaded['timestamp'].dtype == 'int64'
    # update_id 类型
    assert loaded['update_id'].dtype == 'int64'
    # symbol 类型
    assert loaded['symbol'].dtype == 'object'


def test_read_range_returns_rows(monkeypatch, tmp_path: Path):
    """read_range 必须能读出 collect_data 写入的行."""
    f = BookTickerFetcher(
        market=MarketType.SPOT, base_dir=tmp_path, symbol='BTCUSDT', interval=None,
    )
    sample_df = pd.DataFrame({
        'update_id': [1, 2, 3],
        'symbol': ['BTCUSDT', 'BTCUSDT', 'BTCUSDT'],
        'best_bid_price': [100.0, 101.0, 102.0],
        'best_bid_qty': [1.0, 2.0, 3.0],
        'best_ask_price': [101.0, 102.0, 103.0],
        'best_ask_qty': [1.5, 2.5, 3.5],
        'timestamp': [1700000000000, 1700000000001, 1700000000002],
    })

    def fake_run_async(self, coro_func, *args):
        return sample_df

    monkeypatch.setattr(BookTickerFetcher, '_run_async', fake_run_async)
    f.collect_data(symbols=['BTCUSDT'], start='2024-12-01', end='2024-12-01', mode='inc')

    result = f.read_range(
        symbol='BTCUSDT',
        start_time=1733011200000,
        end_time=1733097600000,
        limit=10,
        offset=0,
    )
    assert result['total'] == 3
    assert len(result['rows']) == 3
    assert result['rows'][0]['update_id'] == 1
    assert result['truncated'] is False
