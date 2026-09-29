"""ParquetDataProvider 路径布局单元测试。

真实采集落盘布局（与 exchange/*/downloader、backtest/service 一致）：
    {source}/crypto/{spot|future}/klines/{interval}/{SYMBOL}.parquet

历史实现误指向旧布局 {source}/{market}/{interval}/，导致因子分析与数据质量
检查都读不到 K 线。这里用 tmp_path 固化正确布局，防止回归。
"""

from __future__ import annotations

import pandas as pd
import pytest

from quality.parquet_provider import ParquetDataProvider

TS_BASE = 1_704_067_200_000_000_000
HOUR_NS = 3_600_000_000_000


def _klines_df(rows: int = 2, *, start: int = TS_BASE) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": [start + i * HOUR_NS for i in range(rows)],
            "open": [100.0 + i for i in range(rows)],
            "high": [102.0 + i for i in range(rows)],
            "low": [98.0 + i for i in range(rows)],
            "close": [101.0 + i for i in range(rows)],
            "volume": [1000.0 + i for i in range(rows)],
        }
    )


@pytest.fixture
def source_dir(tmp_path):
    """构造 crypto 布局的临时数据源。"""
    source = tmp_path / "source"
    layout = {
        ("spot", "1h", "BTCUSDT"): _klines_df(2),
        ("spot", "15m", "BTCUSDT"): _klines_df(3),
        ("spot", "1h", "ETHUSDT"): _klines_df(1),
        ("future", "1h", "BTCUSDT"): _klines_df(1),
    }
    for (market, interval, symbol), df in layout.items():
        folder = source / "crypto" / market / "klines" / interval
        folder.mkdir(parents=True, exist_ok=True)
        df.to_parquet(folder / f"{symbol}.parquet", index=False)
    return source


@pytest.fixture
def provider(source_dir):
    return ParquetDataProvider(base_dir=source_dir)


def test_get_kline_data_reads_crypto_layout(provider):
    df = provider.get_kline_data("BTCUSDT", "1h", "spot")
    assert len(df) == 2
    assert "close" in df.columns
    assert df["close"].tolist() == [101.0, 102.0]


def test_get_kline_data_normalizes_slash_symbol(provider):
    # 部分入口传入 "BTC/USDT"，应与裸符号等价
    df = provider.get_kline_data("BTC/USDT", "1h", "spot")
    assert len(df) == 2


def test_get_kline_data_missing_raises(provider):
    with pytest.raises(FileNotFoundError):
        provider.get_kline_data("DOGEUSDT", "1h", "spot")


def test_candle_type_isolation(provider):
    # future 与 spot 同名文件互不串读
    spot = provider.get_kline_data("BTCUSDT", "1h", "spot")
    future = provider.get_kline_data("BTCUSDT", "1h", "future")
    assert len(spot) == 2
    assert len(future) == 1


def test_list_available_symbols_aggregates_intervals(provider):
    symbols = {item["symbol"]: item["intervals"] for item in provider.list_available_symbols("spot")}
    assert symbols["BTCUSDT"] == ["15m", "1h"]
    assert symbols["ETHUSDT"] == ["1h"]


def test_list_available_symbols_filter_interval(provider):
    symbols = provider.list_available_symbols("spot", interval="1h")
    assert {item["symbol"] for item in symbols} == {"BTCUSDT", "ETHUSDT"}
    assert all(item["intervals"] == ["1h"] for item in symbols)


def test_list_available_symbols_empty_when_root_absent(tmp_path):
    provider = ParquetDataProvider(base_dir=tmp_path / "no_such_source")
    assert provider.list_available_symbols("spot") == []


def test_get_available_intervals(provider):
    assert provider.get_available_intervals("BTCUSDT", "spot") == ["15m", "1h"]
    assert provider.get_available_intervals("ETHUSDT", "spot") == ["1h"]


def test_dataprovider_interface_members(provider):
    # DataProvider 抽象接口委托方法
    assert set(provider.list_symbols("spot")) == {"BTCUSDT", "ETHUSDT"}
    assert provider.list_intervals("BTCUSDT", "spot") == ["15m", "1h"]


def test_get_kline_data_column_projection(provider):
    # 只投影需要的列，不返回无关列
    df = provider.get_kline_data("BTCUSDT", "1h", "spot", columns=["timestamp", "close"])
    assert set(df.columns) == {"timestamp", "close"}
    assert df["close"].tolist() == [101.0, 102.0]


def test_get_kline_data_projection_ignores_missing_columns(provider):
    # fixture parquet 没有 quote_volume；投影含缺失列时不报错，只回存在的交集列
    df = provider.get_kline_data("BTCUSDT", "1h", "spot", columns=["close", "quote_volume", "nonexistent"])
    assert set(df.columns) == {"close"}


def test_get_kline_data_default_returns_all_columns(provider):
    # columns=None 时行为不变（全量列）
    df = provider.get_kline_data("BTCUSDT", "1h", "spot")
    assert {"timestamp", "open", "high", "low", "close", "volume"} <= set(df.columns)
