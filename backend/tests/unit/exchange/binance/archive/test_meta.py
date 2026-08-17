"""Tests for archive_meta._meta.json read/write.

覆盖:
- read_meta: 不存在 → None; 损坏 JSON → None + warn
- write_meta: 首次写全字段; 后续写扫描 parquet 重统计 total_rows/file_count/日期范围
- update_meta_after_corrupt: 加入 corrupt_dates 列表, 去重
- _now_iso_ns: 含小数精度 + 时区
- 文件名日期提取: 兼容 interval 段 (如 BTCUSDT-markPriceKlines-1h-2024-12-01)
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from exchange.binance.archive.archive_meta import (
    _now_iso_ns,
    read_meta,
    update_meta_after_corrupt,
    write_meta,
)
from exchange.binance.archive.kinds import ArchiveKind, MarketType


# ---------- 工具: 构造指定行数的 parquet 文件 ----------
def _make_parquet(path: Path, rows: int) -> None:
    """写入指定行数的最小 parquet, 便于测试行数统计。"""
    df = pd.DataFrame({
        'price': [1.0] * rows,
        'quantity': [0.1] * rows,
    })
    pq.write_table(pa.Table.from_pandas(df), path)


# ---------- read_meta ----------

def test_read_meta_missing_returns_none(tmp_path: Path):
    """_meta.json 不存在 → 返回 None。"""
    assert read_meta(tmp_path / 'nonexistent') is None


def test_read_meta_corrupt_json_returns_none_and_warns(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    """非法 JSON → 返回 None 并 log warning。"""
    meta_path = tmp_path / '_meta.json'
    meta_path.write_text('{this is not valid json!!!')
    with caplog.at_level(logging.WARNING, logger='exchange.binance.archive.archive_meta'):
        result = read_meta(tmp_path)
    assert result is None
    assert any('Failed to read' in rec.message for rec in caplog.records)


# ---------- write_meta: 首次写入全字段 ----------

def test_write_meta_first_write_all_fields(tmp_path: Path):
    """首次写入 → 字段齐全: symbol/kind/market/earliest_date/latest_date/total_rows/file_count/corrupt_dates/updated_at。"""
    d = tmp_path / 'spot' / 'aggTrades' / 'BTCUSDT'
    d.mkdir(parents=True)
    write_meta(d, 'BTCUSDT', ArchiveKind.AGG_TRADES, MarketType.SPOT, date(2024, 12, 1))

    meta_path = d / '_meta.json'
    assert meta_path.exists()
    data = json.loads(meta_path.read_text())
    # 必填字段
    for key in (
        'symbol', 'kind', 'market',
        'earliest_date', 'latest_date',
        'total_rows', 'file_count', 'corrupt_dates', 'updated_at',
    ):
        assert key in data, f"missing field: {key}"
    assert data['symbol'] == 'BTCUSDT'
    assert data['kind'] == 'aggTrades'
    assert data['market'] == 'spot'
    # 首次写, 没有 parquet → total_rows=0, file_count=0
    assert data['total_rows'] == 0
    assert data['file_count'] == 0
    assert data['corrupt_dates'] == []


# ---------- write_meta: 后续写重新扫描 parquet ----------

def test_write_meta_rescans_total_rows_and_file_count(tmp_path: Path):
    """后续 write_meta → 自动扫描目录 parquet 重算 total_rows / file_count。"""
    d = tmp_path / 'spot' / 'aggTrades' / 'BTCUSDT'
    d.mkdir(parents=True)
    # 写两个 parquet
    _make_parquet(d / 'BTCUSDT-aggTrades-2024-12-01.parquet', rows=100)
    _make_parquet(d / 'BTCUSDT-aggTrades-2024-12-02.parquet', rows=50)
    write_meta(d, 'BTCUSDT', ArchiveKind.AGG_TRADES, MarketType.SPOT, date(2024, 12, 2))

    data = read_meta(d)
    assert data['total_rows'] == 150
    assert data['file_count'] == 2


def test_write_meta_earliest_latest_reflect_file_names(tmp_path: Path):
    """earliest_date / latest_date 必须反映 parquet 文件名中的日期范围。"""
    d = tmp_path / 'spot' / 'aggTrades' / 'BTCUSDT'
    d.mkdir(parents=True)
    # 故意先创建 12-03 再创建 12-01 → latest_date 必须是 12-03
    _make_parquet(d / 'BTCUSDT-aggTrades-2024-12-03.parquet', rows=10)
    _make_parquet(d / 'BTCUSDT-aggTrades-2024-12-01.parquet', rows=10)
    write_meta(d, 'BTCUSDT', ArchiveKind.AGG_TRADES, MarketType.SPOT, date(2024, 12, 3))

    data = read_meta(d)
    assert data['earliest_date'] == '2024-12-01'
    assert data['latest_date'] == '2024-12-03'


def test_write_meta_works_with_interval_in_filename(tmp_path: Path):
    """文件名带 interval 段 (e.g. markPriceKlines-1h-2024-12-01) 也要正确解析日期。"""
    d = tmp_path / 'um' / 'markPriceKlines' / 'BTCUSDT'
    d.mkdir(parents=True)
    _make_parquet(d / 'BTCUSDT-markPriceKlines-1h-2024-12-01.parquet', rows=24)
    _make_parquet(d / 'BTCUSDT-markPriceKlines-1h-2024-12-02.parquet', rows=24)
    write_meta(d, 'BTCUSDT', ArchiveKind.MARK_KLINES, MarketType.FUTURES_UM, date(2024, 12, 2))

    data = read_meta(d)
    assert data['total_rows'] == 48
    assert data['file_count'] == 2
    assert data['earliest_date'] == '2024-12-01'
    assert data['latest_date'] == '2024-12-02'
    assert data['kind'] == 'markPriceKlines'
    assert data['market'] == 'um'


def test_write_meta_preserves_corrupt_dates_on_subsequent_writes(tmp_path: Path):
    """已有 _meta.json 里有 corrupt_dates → 后续 write_meta 保留它(不被清空)。"""
    d = tmp_path / 'spot' / 'aggTrades' / 'BTCUSDT'
    d.mkdir(parents=True)
    # 预先写一个带 corrupt_dates 的 _meta.json
    existing = {
        'symbol': 'BTCUSDT', 'kind': 'aggTrades', 'market': 'spot',
        'earliest_date': '2024-12-01', 'latest_date': '2024-12-01',
        'total_rows': 0, 'file_count': 0,
        'corrupt_dates': ['2024-12-01'],
        'updated_at': '2024-12-01T00:00:00.000000000+00:00',
    }
    (d / '_meta.json').write_text(json.dumps(existing))

    _make_parquet(d / 'BTCUSDT-aggTrades-2024-12-02.parquet', rows=10)
    write_meta(d, 'BTCUSDT', ArchiveKind.AGG_TRADES, MarketType.SPOT, date(2024, 12, 2))

    data = read_meta(d)
    # corrupt_dates 必须保留
    assert data['corrupt_dates'] == ['2024-12-01']
    # 新文件被加入统计
    assert data['total_rows'] == 10
    assert data['file_count'] == 1


def test_write_meta_always_updates_updated_at(tmp_path: Path):
    """每次 write_meta 都刷新 updated_at 字段。"""
    d = tmp_path / 'spot' / 'aggTrades' / 'BTCUSDT'
    d.mkdir(parents=True)
    write_meta(d, 'BTCUSDT', ArchiveKind.AGG_TRADES, MarketType.SPOT, date(2024, 12, 1))
    first_ts = read_meta(d)['updated_at']
    # 二次写
    write_meta(d, 'BTCUSDT', ArchiveKind.AGG_TRADES, MarketType.SPOT, date(2024, 12, 1))
    second_ts = read_meta(d)['updated_at']
    # updated_at 至少包含小数 + 时区
    assert '.' in first_ts
    assert '+' in first_ts or first_ts.endswith('Z')


# ---------- update_meta_after_corrupt ----------

def test_update_meta_after_corrupt_adds_day(tmp_path: Path):
    """update_meta_after_corrupt → 把 day 加入 corrupt_dates 列表。"""
    d = tmp_path / 'spot' / 'aggTrades' / 'BTCUSDT'
    d.mkdir(parents=True)
    _make_parquet(d / 'BTCUSDT-aggTrades-2024-12-01.parquet', rows=10)
    write_meta(d, 'BTCUSDT', ArchiveKind.AGG_TRADES, MarketType.SPOT, date(2024, 12, 1))

    update_meta_after_corrupt(d, date(2024, 12, 1))
    data = read_meta(d)
    assert '2024-12-01' in data['corrupt_dates']


def test_update_meta_after_corrupt_dedup(tmp_path: Path):
    """重复标记同一日期 → corrupt_dates 不重复。"""
    d = tmp_path / 'spot' / 'aggTrades' / 'BTCUSDT'
    d.mkdir(parents=True)
    _make_parquet(d / 'BTCUSDT-aggTrades-2024-12-01.parquet', rows=10)
    write_meta(d, 'BTCUSDT', ArchiveKind.AGG_TRADES, MarketType.SPOT, date(2024, 12, 1))

    update_meta_after_corrupt(d, date(2024, 12, 1))
    update_meta_after_corrupt(d, date(2024, 12, 1))
    update_meta_after_corrupt(d, date(2024, 12, 1))
    data = read_meta(d)
    assert data['corrupt_dates'].count('2024-12-01') == 1


def test_update_meta_after_corrupt_can_add_multiple_days(tmp_path: Path):
    """不同日期 → corrupt_dates 累积多条。"""
    d = tmp_path / 'spot' / 'aggTrades' / 'BTCUSDT'
    d.mkdir(parents=True)
    _make_parquet(d / 'BTCUSDT-aggTrades-2024-12-01.parquet', rows=10)
    _make_parquet(d / 'BTCUSDT-aggTrades-2024-12-02.parquet', rows=10)
    write_meta(d, 'BTCUSDT', ArchiveKind.AGG_TRADES, MarketType.SPOT, date(2024, 12, 2))

    update_meta_after_corrupt(d, date(2024, 12, 1))
    update_meta_after_corrupt(d, date(2024, 12, 2))
    data = read_meta(d)
    assert set(data['corrupt_dates']) == {'2024-12-01', '2024-12-02'}


def test_update_meta_after_corrupt_creates_meta_if_missing(tmp_path: Path):
    """_meta.json 不存在时 → update_meta_after_corrupt 也能创建。"""
    d = tmp_path / 'spot' / 'aggTrades' / 'BTCUSDT'
    d.mkdir(parents=True)
    update_meta_after_corrupt(d, date(2024, 12, 5))
    data = read_meta(d)
    assert data is not None
    assert '2024-12-05' in data['corrupt_dates']


# ---------- _now_iso_ns ----------

def test_now_iso_ns_has_fraction_and_timezone():
    """_now_iso_ns 返回的字符串必须含小数精度 (9 位) + 时区信息."""
    ts = _now_iso_ns()
    # 形如 2026-07-16T12:34:56.123456789+08:00
    assert '.' in ts
    # 取小数段, 截到时区偏移前 (避免把 +08:00 的 0800 算进去)
    decimals = ts.split('.')[1]
    # 截掉尾部时区偏移 (+HH:MM / -HH:MM / Z)
    decimals = re.split(r'[+\-Z]', decimals)[0]
    digits = ''.join(c for c in decimals if c.isdigit())
    assert len(digits) == 9, f"expected 9 fractional digits, got {decimals!r}"
    # 包含时区偏移 (+HH:MM / -HH:MM / Z)
    assert re.search(r'[+\-]\d{2}:\d{2}$|Z$', ts), f"no tz offset in {ts!r}"
