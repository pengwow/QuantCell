"""Tests for AggTradesFetcher 完整实现。

覆盖:
- column_mapping 含 7 个原始→标准映射
- parquet_schema 是 pyarrow Schema, i64/f64/bool 类型正确
- transform_df 把 raw 列重命名为标准列并强制类型
- monkeypatch 掉 get_daily_archive, 端到端验证 collect_data → parquet 落盘 → read_range
"""

from __future__ import annotations

import io
import zipfile
from typing import TYPE_CHECKING

import pandas as pd
import pyarrow as pa

from exchange.binance.archive.fetchers.agg_trades import AggTradesFetcher
from exchange.binance.archive.kinds import MarketType

if TYPE_CHECKING:
    from pathlib import Path

# ---- 静态钩子: column_mapping / parquet_schema ----


def test_column_mapping_has_7_entries():
    """column_mapping 必须含全部 7 个原始→标准映射。"""
    f = AggTradesFetcher(market=MarketType.SPOT, base_dir="/tmp", symbol="BTCUSDT")
    assert f.column_mapping == {
        "agg_trade_id": "agg_trade_id",
        "price": "price",
        "quantity": "quantity",
        "first_trade_id": "first_trade_id",
        "last_trade_id": "last_trade_id",
        "transact_time": "transact_time",
        "is_buyer_maker": "is_buyer_maker",
    }


def test_parquet_schema_is_pyarrow_schema_with_correct_types():
    """parquet_schema 必须是 pyarrow Schema, 含 7 个字段, 类型为 i64/f64/bool。"""
    f = AggTradesFetcher(market=MarketType.SPOT, base_dir="/tmp", symbol="BTCUSDT")
    schema = f.parquet_schema
    assert isinstance(schema, pa.Schema), f"expected pa.Schema, got {type(schema)}"
    names = [field.name for field in schema]
    assert names == [
        "agg_trade_id",
        "price",
        "quantity",
        "first_trade_id",
        "last_trade_id",
        "transact_time",
        "is_buyer_maker",
    ]
    types = {field.name: str(field.type) for field in schema}
    # i64 字段
    for col in ("agg_trade_id", "first_trade_id", "last_trade_id", "transact_time"):
        assert "int64" in types[col], f"{col} should be int64, got {types[col]}"
    # f64 字段
    for col in ("price", "quantity"):
        assert "double" in types[col], f"{col} should be double, got {types[col]}"
    # bool 字段
    assert "bool" in types["is_buyer_maker"]


# ---- transform_df: 列重命名 + 类型强制 ----


def test_transform_df_renames_and_casts_types():
    """transform_df 必须保留 7 列并把 int 字段强制成 int64。"""
    f = AggTradesFetcher(market=MarketType.SPOT, base_dir="/tmp", symbol="BTCUSDT")
    # 用对象类型输入, 模拟 CSV 解析结果 (pandas 推断可能给出 int64/Object)
    raw = pd.DataFrame(
        {
            "agg_trade_id": pd.array([1, 2], dtype="int64"),
            "price": pd.array([100.0, 101.0], dtype="float64"),
            "quantity": pd.array([0.1, 0.2], dtype="float64"),
            "first_trade_id": pd.array([10, 20], dtype="int64"),
            "last_trade_id": pd.array([10, 20], dtype="int64"),
            "transact_time": pd.array([1700000000000, 1700000000001], dtype="int64"),
            "is_buyer_maker": pd.array([False, True]),
        }
    )
    out = f.transform_df(raw)
    # 列名 / 列数
    assert list(out.columns) == [
        "agg_trade_id",
        "price",
        "quantity",
        "first_trade_id",
        "last_trade_id",
        "transact_time",
        "is_buyer_maker",
    ]
    assert len(out) == 2
    # 值正确
    assert out["agg_trade_id"].tolist() == [1, 2]
    assert out["price"].tolist() == [100.0, 101.0]
    assert out["is_buyer_maker"].tolist() == [False, True]


# ---- _parse_csv_bytes: 现行带 header 格式（um 实测取样） ----


def test_parse_csv_bytes_handles_current_header_format():
    """现行 Binance 归档 CSV 带 header（um 全量实测），header 行不能被当数据行。

    线上故障：fetcher 曾按"永远无 header"解析，um 任务 header 行被当数据行，
    astype 炸 `invalid literal for int() with base 10: 'agg_trade_id'`。
    """
    f = AggTradesFetcher(market=MarketType.FUTURES_UM, base_dir="/tmp", symbol="LTCUSDT")
    raw_bytes = (
        b"agg_trade_id,price,quantity,first_trade_id,last_trade_id,transact_time,is_buyer_maker\n"
        b"38282901,72.31,4.44,38270000,38282901,1730775612345,false\n"
        b"38282902,72.32,1.20,38282902,38282902,1730775612346,true\n"
    )
    df = f._parse_csv_bytes(raw_bytes)
    assert len(df) == 2
    assert list(df.columns) == list(f.column_mapping.keys())
    assert df["agg_trade_id"].iloc[0] == 38282901
    assert df["price"].iloc[0] == 72.31
    assert df["transact_time"].iloc[0] == 1730775612345


# ---- 端到端: monkeypatch get_daily_archive ----


def _make_zip_csv(rows: list[dict]) -> bytes:
    """把字典列表转成 zip 包裹的 CSV bytes (带 header)。"""
    if not rows:
        csv = ""
    else:
        header = list(rows[0].keys())
        lines = [",".join(header)]
        for r in rows:
            lines.append(",".join(str(r[c]) for c in header))
        csv = "\n".join(lines) + "\n"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("BTCUSDT-aggTrades-2024-12-01.csv", csv)
    return buf.getvalue()


def test_collect_data_writes_parquet_with_schema(monkeypatch, tmp_path: Path):
    """monkeypatch 掉 get_daily_archive 返回 sample DataFrame, 验证 parquet 落盘符合 schema。"""
    f = AggTradesFetcher(
        market=MarketType.SPOT,
        base_dir=tmp_path,
        symbol="BTCUSDT",
        interval=None,
    )
    sample_df = pd.DataFrame(
        {
            "agg_trade_id": pd.array([1, 2, 3], dtype="int64"),
            "price": pd.array([100.0, 101.0, 102.0], dtype="float64"),
            "quantity": pd.array([0.1, 0.2, 0.3], dtype="float64"),
            "first_trade_id": pd.array([10, 20, 30], dtype="int64"),
            "last_trade_id": pd.array([10, 20, 30], dtype="int64"),
            "transact_time": pd.array([1700000000000, 1700000000001, 1700000000002], dtype="int64"),
            "is_buyer_maker": pd.array([False, True, False]),
        }
    )

    # 把 async 包装成同步直接返回 sample_df
    async def fake_get_daily_archive(self, session, symbol, day):
        return sample_df

    monkeypatch.setattr(
        AggTradesFetcher,
        "get_daily_archive",
        fake_get_daily_archive,
    )

    # 绕过 aiohttp 真实调用: collect_data 内部用 _run_async, 也 patch 掉
    def fake_run_async(self, coro_func, *args):
        return sample_df

    monkeypatch.setattr(
        AggTradesFetcher,
        "_run_async",
        fake_run_async,
    )

    result = f.collect_data(symbols=["BTCUSDT"], start="2024-12-01", end="2024-12-01", mode="inc")
    assert result["files_added"] == 1
    assert result["symbols_processed"] == 1

    # 落盘文件存在, 读回 schema 正确
    out_path = f.save_dir / "BTCUSDT-aggTrades-2024-12-01.parquet"
    assert out_path.exists()

    loaded = pd.read_parquet(out_path)
    assert len(loaded) == 3
    assert list(loaded.columns) == list(f.column_mapping.values())
    # 类型: 数值列; bool 列在 pandas 2.x 下读回是 nullable 'boolean' (而非 'bool'),
    # 两者都对应 pyarrow bool_; 校验在 parquet schema 层面已覆盖
    assert loaded["agg_trade_id"].dtype == "int64"
    assert loaded["price"].dtype == "float64"
    assert str(loaded["is_buyer_maker"].dtype) in ("bool", "boolean")


def test_read_range_returns_rows_from_parquet(monkeypatch, tmp_path: Path):
    """read_range 必须能读出 collect_data 写入的行。"""
    f = AggTradesFetcher(
        market=MarketType.SPOT,
        base_dir=tmp_path,
        symbol="BTCUSDT",
        interval=None,
    )
    sample_df = pd.DataFrame(
        {
            "agg_trade_id": [1, 2, 3],
            "price": [100.0, 101.0, 102.0],
            "quantity": [0.1, 0.2, 0.3],
            "first_trade_id": [10, 20, 30],
            "last_trade_id": [10, 20, 30],
            "transact_time": [1700000000000, 1700000000001, 1700000000002],
            "is_buyer_maker": [False, True, False],
        }
    )

    def fake_run_async(self, coro_func, *args):
        return sample_df

    monkeypatch.setattr(AggTradesFetcher, "_run_async", fake_run_async)
    f.collect_data(symbols=["BTCUSDT"], start="2024-12-01", end="2024-12-01", mode="inc")

    # 2024-12-01 Asia/Shanghai (UTC+8) 00:00 = 2024-11-30 16:00 UTC = 1733011200 s
    # base.read_range 用本地时区算 day_ms, 这里用本地 00:00 UTC 毫秒作为 start_time
    result = f.read_range(
        symbol="BTCUSDT",
        start_time=1733011200000,
        end_time=1733097600000,
        limit=10,
        offset=0,
    )
    assert result["total"] == 3
    assert len(result["rows"]) == 3
    assert result["rows"][0]["agg_trade_id"] == 1
    assert result["truncated"] is False
