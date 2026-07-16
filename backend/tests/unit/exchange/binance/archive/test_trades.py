"""Tests for TradesFetcher 完整实现。

覆盖:
- column_mapping 含 6 个原始→标准映射 (id, price, qty, quote_qty, time, is_buyer_maker)
- parquet_schema 6 列, i64/f64/bool 类型正确
- _parse_csv_bytes 处理无 header 的 CSV (trades zip 内 CSV 不带 header)
- monkeypatch 端到端: collect_data → parquet 落盘 → read_range
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow as pa
import pytest

from exchange.binance.archive.fetchers.trades import TradesFetcher
from exchange.binance.archive.kinds import ArchiveKind, MarketType


# ---- 静态钩子 ----

def test_column_mapping_has_6_entries():
    """column_mapping 必须含全部 6 个原始→标准映射。"""
    f = TradesFetcher(market=MarketType.SPOT, base_dir='/tmp', symbol='BTCUSDT')
    assert f.column_mapping == {
        'id': 'id',
        'price': 'price',
        'qty': 'qty',
        'quote_qty': 'quote_qty',
        'time': 'time',
        'is_buyer_maker': 'is_buyer_maker',
    }


def test_parquet_schema_is_pyarrow_schema_with_correct_types():
    """parquet_schema 必须是 pyarrow Schema, 含 6 列, 类型正确。"""
    f = TradesFetcher(market=MarketType.SPOT, base_dir='/tmp', symbol='BTCUSDT')
    schema = f.parquet_schema
    assert isinstance(schema, pa.Schema), f"expected pa.Schema, got {type(schema)}"
    names = [field.name for field in schema]
    assert names == ['id', 'price', 'qty', 'quote_qty', 'time', 'is_buyer_maker']
    types = {field.name: str(field.type) for field in schema}
    # i64: id, time
    assert 'int64' in types['id']
    assert 'int64' in types['time']
    # f64: price, qty, quote_qty
    for col in ('price', 'qty', 'quote_qty'):
        assert 'double' in types[col], f"{col} should be double, got {types[col]}"
    # bool: is_buyer_maker
    assert 'bool' in types['is_buyer_maker']


# ---- _parse_csv_bytes: trades zip 内 CSV 不带 header ----

def test_parse_csv_bytes_handles_headerless():
    """trades zip 内 CSV 无 header; 必须强制指定列名。"""
    f = TradesFetcher(market=MarketType.SPOT, base_dir='/tmp', symbol='BTCUSDT')
    raw_bytes = (
        b'123,100.0,0.1,10.0,1700000000000,false\n'
        b'124,101.0,0.2,20.2,1700000000001,true\n'
    )
    df = f._parse_csv_bytes(raw_bytes)
    assert len(df) == 2
    # 第一列必须是 'id' (而不是 '123' 被当列名)
    assert df.columns[0] == 'id'
    assert list(df.columns) == ['id', 'price', 'qty', 'quote_qty', 'time', 'is_buyer_maker']
    assert df['id'].iloc[0] == 123
    assert df['price'].iloc[0] == 100.0
    assert df['is_buyer_maker'].iloc[0] is False or df['is_buyer_maker'].iloc[0] == False


# ---- 端到端: monkeypatch _run_async, collect_data → parquet ----

def test_collect_data_writes_parquet_with_schema(monkeypatch, tmp_path: Path):
    """collect_data 写出的 parquet 必须符合 schema, read_range 能读出。"""
    f = TradesFetcher(
        market=MarketType.SPOT, base_dir=tmp_path, symbol='BTCUSDT', interval=None,
    )
    sample_df = pd.DataFrame({
        'id': pd.array([1, 2], dtype='int64'),
        'price': pd.array([100.0, 101.0], dtype='float64'),
        'qty': pd.array([0.1, 0.2], dtype='float64'),
        'quote_qty': pd.array([10.0, 20.2], dtype='float64'),
        'time': pd.array([1700000000000, 1700000000001], dtype='int64'),
        'is_buyer_maker': pd.array([False, True]),
    })

    def fake_run_async(self, coro_func, *args):
        return sample_df

    monkeypatch.setattr(TradesFetcher, '_run_async', fake_run_async)
    result = f.collect_data(symbols=['BTCUSDT'], start='2024-12-01', end='2024-12-01', mode='inc')
    assert result['files_added'] == 1
    assert result['symbols_processed'] == 1

    out_path = f.save_dir / 'BTCUSDT-trades-2024-12-01.parquet'
    assert out_path.exists()

    loaded = pd.read_parquet(out_path)
    assert len(loaded) == 2
    assert list(loaded.columns) == list(f.column_mapping.values())
    # 数值列类型
    assert loaded['id'].dtype == 'int64'
    assert loaded['price'].dtype == 'float64'
    assert str(loaded['is_buyer_maker'].dtype) in ('bool', 'boolean')


def test_read_range_returns_rows(monkeypatch, tmp_path: Path):
    """read_range 必须能读出 collect_data 写入的行。"""
    f = TradesFetcher(
        market=MarketType.SPOT, base_dir=tmp_path, symbol='BTCUSDT', interval=None,
    )
    sample_df = pd.DataFrame({
        'id': [1, 2, 3],
        'price': [100.0, 101.0, 102.0],
        'qty': [0.1, 0.2, 0.3],
        'quote_qty': [10.0, 20.2, 30.6],
        'time': [1700000000000, 1700000000001, 1700000000002],
        'is_buyer_maker': [False, True, False],
    })

    def fake_run_async(self, coro_func, *args):
        return sample_df

    monkeypatch.setattr(TradesFetcher, '_run_async', fake_run_async)
    f.collect_data(symbols=['BTCUSDT'], start='2024-12-01', end='2024-12-01', mode='inc')

    # 2024-12-01 本地 00:00 UTC 毫秒 (与 agg_trades 测试同样的处理)
    result = f.read_range(
        symbol='BTCUSDT',
        start_time=1733011200000,
        end_time=1733097600000,
        limit=10,
        offset=0,
    )
    assert result['total'] == 3
    assert len(result['rows']) == 3
    assert result['rows'][0]['id'] == 1
    assert result['truncated'] is False
