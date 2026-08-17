"""Tests for PremiumIndexKlinesFetcher 完整实现。

覆盖:
- column_mapping 9 个原始→标准映射 (8 个 K 线列 + premium_index)
- parquet_schema 9 列: open_time(i64) open/high/low/close/volume/quote_volume(f64) count(int32) premium_index(f64)
- URL 拼装带 interval
- 端到端: collect_data → parquet 落盘 → read_range
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pytest

from exchange.binance.archive.fetchers.premium_index_klines import (
    PREMIUM_KLINES_SCHEMA,
    PremiumIndexKlinesFetcher,
)
from exchange.binance.archive.kinds import ArchiveKind, KIND_INTERVALS, MarketType


# ---- 静态钩子 ----

def test_column_mapping_has_9_entries():
    """column_mapping 必须含全部 9 个原始→标准映射 (8 K 线列 + premium_index)."""
    f = PremiumIndexKlinesFetcher(
        market=MarketType.FUTURES_UM, base_dir='/tmp', symbol='BTCUSDT', interval='1h',
    )
    assert f.column_mapping == {
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


def test_parquet_schema_has_9_fields_with_correct_types():
    """parquet_schema 9 列: 8 K 线列 + premium_index(f64)."""
    f = PremiumIndexKlinesFetcher(
        market=MarketType.FUTURES_UM, base_dir='/tmp', symbol='BTCUSDT', interval='1h',
    )
    schema = f.parquet_schema
    assert isinstance(schema, pa.Schema), f"expected pa.Schema, got {type(schema)}"
    names = [field.name for field in schema]
    assert names == [
        'open_time', 'open', 'high', 'low',
        'close', 'volume', 'quote_volume', 'count',
        'premium_index',
    ]
    types = {field.name: str(field.type) for field in schema}
    # i64: open_time
    assert 'int64' in types['open_time'], f"open_time type: {types['open_time']}"
    # f64: 6 个价格/数量列
    for col in ('open', 'high', 'low', 'close', 'volume', 'quote_volume'):
        assert 'double' in types[col], f"{col} type: {types[col]}"
    # int32: count
    assert 'int32' in types['count'], f"count type: {types['count']}"
    # f64: premium_index (新增列)
    assert 'double' in types['premium_index'], f"premium_index type: {types['premium_index']}"


def test_kind_intervals_contains_premium_klines_supported():
    """PREMIUM_KLINES 必须在 KIND_INTERVALS 中声明 8 个 interval."""
    assert KIND_INTERVALS[ArchiveKind.PREMIUM_KLINES] == [
        '1m', '3m', '5m', '15m', '30m', '1h', '2h', '1d',
    ]


# ---- URL 拼装 ----

def test_url_contains_interval_segment(tmp_path: Path):
    """URL 必须含 '/1h/' 段 + 文件名带 'premiumIndexKlines-1h-'."""
    f = PremiumIndexKlinesFetcher(
        market=MarketType.FUTURES_UM, base_dir=tmp_path, symbol='BTCUSDT', interval='1h',
    )
    url = f.get_zip_url('BTCUSDT', '2024-12-01')
    assert '/1h/' in url, f"URL must contain /1h/ segment: {url}"
    assert 'premiumIndexKlines-1h-2024-12-01.zip' in url, f"filename wrong: {url}"


def test_save_filename_includes_interval(tmp_path: Path):
    """save_instrument 写出文件名带 interval 段."""
    f = PremiumIndexKlinesFetcher(
        market=MarketType.FUTURES_UM, base_dir=tmp_path, symbol='BTCUSDT', interval='5m',
    )
    df = pd.DataFrame({
        'open_time': pd.array([1700000000000], dtype='int64'),
        'open': pd.array([100.0], dtype='float64'),
        'high': pd.array([101.0], dtype='float64'),
        'low': pd.array([99.0], dtype='float64'),
        'close': pd.array([100.5], dtype='float64'),
        'volume': pd.array([10.0], dtype='float64'),
        'quote_volume': pd.array([1000.0], dtype='float64'),
        'count': pd.array([100], dtype='int32'),
        'premium_index': pd.array([0.001], dtype='float64'),
    })
    p = f.save_instrument('BTCUSDT', date(2024, 12, 1), df)
    assert p is not None
    assert p.exists()
    assert p.name == 'BTCUSDT-premiumIndexKlines-5m-2024-12-01.parquet'


# ---- 端到端 ----

def test_collect_data_writes_parquet_with_schema(monkeypatch, tmp_path: Path):
    """collect_data 写出的 parquet 必须含 premium_index 列, 符合 9 列 schema."""
    f = PremiumIndexKlinesFetcher(
        market=MarketType.FUTURES_UM, base_dir=tmp_path, symbol='BTCUSDT', interval='1h',
    )
    sample_df = pd.DataFrame({
        'open_time': pd.array([1700000000000, 1700003600000], dtype='int64'),
        'open': pd.array([100.0, 101.0], dtype='float64'),
        'high': pd.array([101.0, 102.0], dtype='float64'),
        'low': pd.array([99.0, 100.0], dtype='float64'),
        'close': pd.array([100.5, 101.5], dtype='float64'),
        'volume': pd.array([10.0, 11.0], dtype='float64'),
        'quote_volume': pd.array([1000.0, 1100.0], dtype='float64'),
        'count': pd.array([100, 110], dtype='int32'),
        'premium_index': pd.array([0.001, 0.002], dtype='float64'),
    })

    def fake_run_async(self, coro_func, *args):
        return sample_df

    monkeypatch.setattr(PremiumIndexKlinesFetcher, '_run_async', fake_run_async)
    result = f.collect_data(
        symbols=['BTCUSDT'], start='2024-12-01', end='2024-12-01', mode='inc',
    )
    assert result['files_added'] == 1
    assert result['symbols_processed'] == 1

    out_path = f.save_dir / 'BTCUSDT-premiumIndexKlines-1h-2024-12-01.parquet'
    assert out_path.exists()

    loaded = pd.read_parquet(out_path)
    assert len(loaded) == 2
    assert list(loaded.columns) == [
        'open_time', 'open', 'high', 'low',
        'close', 'volume', 'quote_volume', 'count',
        'premium_index',
    ]
    # premium_index 列保留且类型为 float
    assert 'premium_index' in loaded.columns
    assert loaded['premium_index'].dtype == 'float64'
    assert loaded['premium_index'].iloc[0] == 0.001
    assert loaded['open_time'].dtype == 'int64'


def test_read_range_returns_rows(monkeypatch, tmp_path: Path):
    """read_range 必须能读出 collect_data 写入的行 (含 premium_index)."""
    f = PremiumIndexKlinesFetcher(
        market=MarketType.FUTURES_UM, base_dir=tmp_path, symbol='BTCUSDT', interval='1h',
    )
    sample_df = pd.DataFrame({
        'open_time': [1700000000000, 1700003600000, 1700007200000],
        'open': [100.0, 101.0, 102.0],
        'high': [101.0, 102.0, 103.0],
        'low': [99.0, 100.0, 101.0],
        'close': [100.5, 101.5, 102.5],
        'volume': [10.0, 11.0, 12.0],
        'quote_volume': [1000.0, 1100.0, 1200.0],
        'count': [100, 110, 120],
        'premium_index': [0.001, 0.0015, 0.002],
    })

    def fake_run_async(self, coro_func, *args):
        return sample_df

    monkeypatch.setattr(PremiumIndexKlinesFetcher, '_run_async', fake_run_async)
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
    assert result['rows'][0]['open'] == 100.0
    assert result['rows'][0]['premium_index'] == 0.001
    assert result['truncated'] is False
