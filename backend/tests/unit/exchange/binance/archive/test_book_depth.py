"""Tests for BookDepthFetcher 完整实现（嵌套 bids/asks 展平为长表）。

覆盖:
- column_mapping 为空 dict (列由 transform_df 构造, 不存在 raw→standard 固定映射)
- parquet_schema 6 列: timestamp(i64), symbol(str), side(str), level(i32), price(f64), quantity(f64)
- transform_df 把 nested bids/asks 展平: 1 条记录 → N bids + M asks 行
- side 列在 'bid'/'ask' 之间
- level 列从 0 开始 (0 = 最优)
- 端到端: collect_data → parquet 落盘 → read_range
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd
import pyarrow as pa

from exchange.binance.archive.fetchers.book_depth import (
    BookDepthFetcher,
)
from exchange.binance.archive.kinds import MarketType

if TYPE_CHECKING:
    from pathlib import Path

# ---- 静态钩子 ----


def test_column_mapping_is_empty():
    """bookDepth 列由 transform_df 构造, column_mapping 保持空 dict."""
    f = BookDepthFetcher(market=MarketType.SPOT, base_dir="/tmp", symbol="BTCUSDT")
    assert f.column_mapping == {}


def test_parquet_schema_has_6_fields_with_correct_types():
    """parquet_schema 必须含 6 列: timestamp(i64) symbol(str) side(str) level(i32) price(f64) quantity(f64)."""
    f = BookDepthFetcher(market=MarketType.SPOT, base_dir="/tmp", symbol="BTCUSDT")
    schema = f.parquet_schema
    assert isinstance(schema, pa.Schema), f"expected pa.Schema, got {type(schema)}"
    names = [field.name for field in schema]
    assert names == ["timestamp", "symbol", "side", "level", "price", "quantity"]
    types = {field.name: str(field.type) for field in schema}
    assert "int64" in types["timestamp"], f"timestamp type: {types['timestamp']}"
    assert "string" in types["symbol"], f"symbol type: {types['symbol']}"
    assert "string" in types["side"], f"side type: {types['side']}"
    assert "int32" in types["level"], f"level type: {types['level']}"
    assert "double" in types["price"], f"price type: {types['price']}"
    assert "double" in types["quantity"], f"quantity type: {types['quantity']}"


# ---- transform_df: 嵌套 bids/asks 展平 ----


def test_transform_df_flattens_single_record():
    """1 条记录: bids 2 条 + asks 2 条 → 4 行; side 列在 'bid'/'ask' 之间."""
    f = BookDepthFetcher(market=MarketType.SPOT, base_dir="/tmp", symbol="BTCUSDT")
    raw = pd.DataFrame(
        {
            "timestamp": [1700000000000],
            "symbol": ["BTCUSDT"],
            "bids": [[[100.0, 1.0], [99.0, 2.0]]],
            "asks": [[[101.0, 1.5], [102.0, 2.5]]],
        }
    )
    out = f.transform_df(raw)
    # 1 条 record → 2 bids + 2 asks = 4 行
    assert len(out) == 4
    assert list(out.columns) == [
        "timestamp",
        "symbol",
        "side",
        "level",
        "price",
        "quantity",
    ]
    assert (out["side"] == "bid").sum() == 2
    assert (out["side"] == "ask").sum() == 2


def test_transform_df_flattens_multiple_records():
    """多条记录: 第 1 条 bids 2 + asks 2 = 4 行; 第 2 条 bids 3 + asks 1 = 4 行; 合计 8 行."""
    f = BookDepthFetcher(market=MarketType.SPOT, base_dir="/tmp", symbol="BTCUSDT")
    raw = pd.DataFrame(
        {
            "timestamp": [1700000000000, 1700000001000],
            "symbol": ["BTCUSDT", "BTCUSDT"],
            "bids": [
                [[100.0, 1.0], [99.0, 2.0]],
                [[100.0, 0.5], [99.5, 1.5], [99.0, 2.5]],
            ],
            "asks": [
                [[101.0, 1.5], [102.0, 2.5]],
                [[101.0, 1.0]],
            ],
        }
    )
    out = f.transform_df(raw)
    # 总行数 = 原始 bids 总数 (2+3=5) + asks 总数 (2+1=3) = 8
    assert len(out) == 8
    assert (out["side"] == "bid").sum() == 5
    assert (out["side"] == "ask").sum() == 3


def test_transform_df_level_starts_at_zero_per_record():
    """每条 record 内 level 从 0 开始 (0 = 最优), 不同 record 之间独立计数."""
    f = BookDepthFetcher(market=MarketType.SPOT, base_dir="/tmp", symbol="BTCUSDT")
    raw = pd.DataFrame(
        {
            "timestamp": [1700000000000, 1700000001000],
            "symbol": ["BTCUSDT", "BTCUSDT"],
            "bids": [
                [[100.0, 1.0], [99.0, 2.0]],
                [[100.0, 0.5], [99.5, 1.5]],
            ],
            "asks": [
                [[101.0, 1.5]],
                [[101.0, 1.0], [102.0, 2.0], [103.0, 3.0]],
            ],
        }
    )
    out = f.transform_df(raw)
    # bid 部分的 level 在两个 record 内都从 0 开始
    bid_rows = out[out["side"] == "bid"]
    # 4 个 bid 行: 第 1 条 2 行 (level 0,1) + 第 2 条 2 行 (level 0,1)
    assert bid_rows["level"].tolist() == [0, 1, 0, 1]
    # ask 部分的 level: 第 1 条 1 行 (level 0) + 第 2 条 3 行 (level 0,1,2)
    ask_rows = out[out["side"] == "ask"]
    assert ask_rows["level"].tolist() == [0, 0, 1, 2]


def test_transform_df_drops_original_bids_asks_columns():
    """展平后原始 bids/asks 列不应再出现, 只保留 6 列长表 schema."""
    f = BookDepthFetcher(market=MarketType.SPOT, base_dir="/tmp", symbol="BTCUSDT")
    raw = pd.DataFrame(
        {
            "timestamp": [1700000000000],
            "symbol": ["BTCUSDT"],
            "bids": [[[100.0, 1.0]]],
            "asks": [[[101.0, 1.5]]],
        }
    )
    out = f.transform_df(raw)
    assert "bids" not in out.columns
    assert "asks" not in out.columns
    assert len(out.columns) == 6


def test_transform_df_preserves_values_correctly():
    """验证展平后 price/quantity/timestamp/symbol 值正确传递."""
    f = BookDepthFetcher(market=MarketType.SPOT, base_dir="/tmp", symbol="BTCUSDT")
    raw = pd.DataFrame(
        {
            "timestamp": [1700000000000],
            "symbol": ["ETHUSDT"],
            "bids": [[[100.5, 1.5]]],
            "asks": [[[101.5, 2.5]]],
        }
    )
    out = f.transform_df(raw)
    bid_row = out[out["side"] == "bid"].iloc[0]
    assert bid_row["price"] == 100.5
    assert bid_row["quantity"] == 1.5
    ask_row = out[out["side"] == "ask"].iloc[0]
    assert ask_row["price"] == 101.5
    assert ask_row["quantity"] == 2.5
    # timestamp / symbol 复制到所有行
    assert (out["timestamp"] == 1700000000000).all()
    assert (out["symbol"] == "ETHUSDT").all()


# ---- _parse_csv_bytes: bookDepth zip 内的 CSV 含 bids/asks 嵌套数组 ----


def test_parse_csv_bytes_parses_nested_bids_asks():
    """bookDepth zip 内 CSV 有 bids/asks 嵌套数组列; 必须解析为 Python 列表."""
    f = BookDepthFetcher(market=MarketType.SPOT, base_dir="/tmp", symbol="BTCUSDT")
    raw_bytes = (
        b'timestamp,symbol,bids,asks\n1700000000000,BTCUSDT,"[[100.0,1.0],[99.0,2.0]]","[[101.0,1.5],[102.0,2.5]]"\n'
    )
    df = f._parse_csv_bytes(raw_bytes)
    assert len(df) == 1
    assert df["timestamp"].iloc[0] == 1700000000000
    # bids / asks 必须是 list, 不是 str
    assert isinstance(df["bids"].iloc[0], list)
    assert isinstance(df["asks"].iloc[0], list)
    assert df["bids"].iloc[0] == [[100.0, 1.0], [99.0, 2.0]]
    assert df["asks"].iloc[0] == [[101.0, 1.5], [102.0, 2.5]]


# ---- 端到端: monkeypatch _run_async, collect_data → parquet ----


def test_collect_data_writes_parquet_with_schema(monkeypatch, tmp_path: Path):
    """monkeypatch 掉 _run_async 模拟已展平的 DataFrame, 验证 parquet 落盘符合 schema."""
    f = BookDepthFetcher(
        market=MarketType.SPOT,
        base_dir=tmp_path,
        symbol="BTCUSDT",
        interval=None,
    )
    # 模拟 transform_df 已展平后的 DataFrame
    sample_df = pd.DataFrame(
        {
            "timestamp": pd.array([1700000000000] * 4, dtype="int64"),
            "symbol": ["BTCUSDT"] * 4,
            "side": ["bid", "bid", "ask", "ask"],
            "level": pd.array([0, 1, 0, 1], dtype="int32"),
            "price": pd.array([100.0, 99.0, 101.0, 102.0], dtype="float64"),
            "quantity": pd.array([1.0, 2.0, 1.5, 2.5], dtype="float64"),
        }
    )

    def fake_run_async(self, coro_func, *args):
        return sample_df

    monkeypatch.setattr(BookDepthFetcher, "_run_async", fake_run_async)
    result = f.collect_data(
        symbols=["BTCUSDT"],
        start="2024-12-01",
        end="2024-12-01",
        mode="inc",
    )
    assert result["files_added"] == 1
    assert result["symbols_processed"] == 1

    out_path = f.save_dir / "BTCUSDT-bookDepth-2024-12-01.parquet"
    assert out_path.exists()

    loaded = pd.read_parquet(out_path)
    assert len(loaded) == 4
    assert list(loaded.columns) == [
        "timestamp",
        "symbol",
        "side",
        "level",
        "price",
        "quantity",
    ]
    assert loaded["timestamp"].dtype == "int64"
    assert loaded["level"].dtype == "int32"
    assert loaded["price"].dtype == "float64"
    assert loaded["quantity"].dtype == "float64"


def test_read_range_returns_rows(monkeypatch, tmp_path: Path):
    """read_range 必须能读出 collect_data 写入的行."""
    f = BookDepthFetcher(
        market=MarketType.SPOT,
        base_dir=tmp_path,
        symbol="BTCUSDT",
        interval=None,
    )
    sample_df = pd.DataFrame(
        {
            "timestamp": [1700000000000, 1700000000000, 1700000000000, 1700000000000],
            "symbol": ["BTCUSDT"] * 4,
            "side": ["bid", "bid", "ask", "ask"],
            "level": [0, 1, 0, 1],
            "price": [100.0, 99.0, 101.0, 102.0],
            "quantity": [1.0, 2.0, 1.5, 2.5],
        }
    )

    def fake_run_async(self, coro_func, *args):
        return sample_df

    monkeypatch.setattr(BookDepthFetcher, "_run_async", fake_run_async)
    f.collect_data(symbols=["BTCUSDT"], start="2024-12-01", end="2024-12-01", mode="inc")

    result = f.read_range(
        symbol="BTCUSDT",
        start_time=1733011200000,
        end_time=1733097600000,
        limit=10,
        offset=0,
    )
    assert result["total"] == 4
    assert len(result["rows"]) == 4
    assert result["rows"][0]["side"] == "bid"
    assert result["truncated"] is False
