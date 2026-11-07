"""Tests for BaseBinanceArchiveDownloader shared base class."""

from datetime import date
from typing import TYPE_CHECKING

import pytest

from exchange.binance.archive.base import (
    BaseBinanceArchiveDownloader,
    read_csv_with_header_sniff,
)
from exchange.binance.archive.kinds import ArchiveKind, MarketType

if TYPE_CHECKING:
    import pandas as pd


class _StubFetcher(BaseBinanceArchiveDownloader):
    """最小 fetcher：重写 4 个钩子，不做真实下载。"""

    archive_kind = ArchiveKind.AGG_TRADES
    url_subpath = "aggTrades"
    column_mapping = {"a": "price", "b": "qty"}
    parquet_schema = None

    def transform_df(self, raw_df: pd.DataFrame) -> pd.DataFrame:
        return raw_df.rename(columns={"a": "price", "b": "qty"})


def test_init_resolves_save_dir(tmp_path):
    fetcher = _StubFetcher(market=MarketType.SPOT, base_dir=tmp_path, symbol="BTCUSDT", interval=None)
    assert fetcher.save_dir == tmp_path / "spot" / "aggTrades" / "BTCUSDT"
    assert fetcher.market == MarketType.SPOT


def test_get_zip_url_calls_kinds_builder(tmp_path):
    fetcher = _StubFetcher(market=MarketType.SPOT, base_dir=tmp_path, symbol="BTCUSDT", interval=None)
    url = fetcher.get_zip_url("BTCUSDT", "2024-12-01")
    assert "data.binance.vision/data/spot/daily/aggTrades/BTCUSDT" in url
    assert "2024-12-01.zip" in url


def test_calculate_missing_ranges_full_mode_includes_all(tmp_path):
    fetcher = _StubFetcher(market=MarketType.SPOT, base_dir=tmp_path, symbol="BTCUSDT", interval=None)
    fetcher.save_dir.mkdir(parents=True, exist_ok=True)
    (fetcher.save_dir / "BTCUSDT-aggTrades-2024-12-02.parquet").touch()

    ranges = fetcher._calculate_missing_ranges(start=date(2024, 12, 1), end=date(2024, 12, 3), mode="full")
    assert len(ranges) == 3
    assert ranges[0] == (date(2024, 12, 1), date(2024, 12, 1))
    assert ranges[-1] == (date(2024, 12, 3), date(2024, 12, 3))


def test_calculate_missing_ranges_inc_mode_skips_existing(tmp_path):
    fetcher = _StubFetcher(market=MarketType.SPOT, base_dir=tmp_path, symbol="BTCUSDT", interval=None)
    fetcher.save_dir.mkdir(parents=True, exist_ok=True)
    (fetcher.save_dir / "BTCUSDT-aggTrades-2024-12-02.parquet").touch()

    ranges = fetcher._calculate_missing_ranges(start=date(2024, 12, 1), end=date(2024, 12, 3), mode="inc")
    missing_dates = {d for r in ranges for d in r}
    assert missing_dates == {date(2024, 12, 1), date(2024, 12, 3)}


def test_read_range_with_no_files_returns_empty(tmp_path):
    fetcher = _StubFetcher(market=MarketType.SPOT, base_dir=tmp_path, symbol="BTCUSDT", interval=None)
    result = fetcher.read_range(
        symbol="BTCUSDT",
        start_time=1700000000000,
        end_time=1800000000000,
        limit=100,
        offset=0,
    )
    assert result["total"] == 0
    assert result["rows"] == []


def test_collect_data_no_symbols_returns_empty(tmp_path):
    fetcher = _StubFetcher(market=MarketType.SPOT, base_dir=tmp_path, symbol="BTCUSDT", interval=None)
    result = fetcher.collect_data(symbols=[], start="2024-12-01", end="2024-12-02", mode="inc")
    assert result == {"files_added": 0, "symbols_processed": 0}


def test_collect_data_all_fail_raises(tmp_path, monkeypatch):
    """全败必须诚实上抛，禁止零落盘假成功（历史上任务曾显示 100% 而磁盘无文件）。"""

    def _boom(self, coro_func, *args):
        raise ConnectionError("network down")

    monkeypatch.setattr(BaseBinanceArchiveDownloader, "_run_async", _boom)
    fetcher = _StubFetcher(market=MarketType.SPOT, base_dir=tmp_path, symbol="BTCUSDT", interval=None)
    with pytest.raises(RuntimeError, match="全部失败"):
        fetcher.collect_data(symbols=["BTCUSDT"], start="2024-12-01", end="2024-12-02", mode="inc")


def test_collect_data_partial_fail_no_raise(tmp_path, monkeypatch):
    """部分失败不炸：增量语义下成功日期已落盘，未落盘日期下次运行补。"""
    real_run = BaseBinanceArchiveDownloader._run_async
    calls = {"n": 0}

    def _flaky(self, coro_func, *args):
        calls["n"] += 1
        if calls["n"] == 1:  # 第一天失败
            raise ConnectionError("network down")
        import pandas as pd

        return pd.DataFrame({"a": [1.0], "b": [1.0]})

    monkeypatch.setattr(BaseBinanceArchiveDownloader, "_run_async", _flaky)
    fetcher = _StubFetcher(market=MarketType.SPOT, base_dir=tmp_path, symbol="BTCUSDT", interval=None)
    result = fetcher.collect_data(symbols=["BTCUSDT"], start="2024-12-01", end="2024-12-02", mode="inc")
    assert result["files_added"] == 1
    assert real_run is not None


def test_collect_data_empty_day_creates_no_shell_dir(tmp_path, monkeypatch):
    """全 404（逐日空 DataFrame）必须显性报错且不留目录。

    两个守护点：
    1. 不许假成功——bookTicker um 实测 Binance 无数据时任务报 completed
       "下载完成"，用户在浏览页只看到 0 行却查不到原因；
    2. 不留空壳——write_meta 会 mkdir，空数据日若写 meta 会留下
       "归档树显示 symbol 但点开 0 行"的空壳目录。
    """
    import pandas as pd

    def _empty(self, coro_func, *args):
        # 模拟 404：get_daily_archive 返回空 DataFrame
        return pd.DataFrame()

    monkeypatch.setattr(BaseBinanceArchiveDownloader, "_run_async", _empty)
    fetcher = _StubFetcher(market=MarketType.SPOT, base_dir=tmp_path, symbol="BTCUSDT", interval=None)
    with pytest.raises(RuntimeError, match=r"均不可得|404"):
        fetcher.collect_data(symbols=["BTCUSDT"], start="2024-12-01", end="2024-12-02", mode="inc")
    assert not fetcher.save_dir.exists(), "空数据日不应创建任何目录（meta 空壳）"


def test_collect_data_mixed_empty_and_success_no_raise(tmp_path, monkeypatch):
    """404 日与成功日混合时正常完成且空日不留目录（增量语义：可得的日期先落盘）。"""
    import pandas as pd

    calls = {"n": 0}

    def _one_day_empty(self, coro_func, *args):
        calls["n"] += 1
        return pd.DataFrame() if calls["n"] == 1 else pd.DataFrame({"a": [1.0], "b": [1.0]})

    monkeypatch.setattr(BaseBinanceArchiveDownloader, "_run_async", _one_day_empty)
    fetcher = _StubFetcher(market=MarketType.SPOT, base_dir=tmp_path, symbol="BTCUSDT", interval=None)
    result = fetcher.collect_data(symbols=["BTCUSDT"], start="2024-12-01", end="2024-12-02", mode="inc")
    assert result["files_added"] == 1


# ---- read_csv_with_header_sniff: Binance 归档 CSV 新旧两种格式 ----


def test_read_csv_with_header_sniff_skips_header_row():
    """现行 Binance 归档 CSV 带 header（futures 全量 / spot 2020 后），header 行不能被当数据行。

    线上故障：fetcher 按"永远无 header"解析，header 行混入数据后
    astype(int) 炸 `invalid literal for int() with base 10: 'agg_trade_id'`。
    """
    data = b"agg_trade_id,price,quantity\n1,100.0,0.1\n2,101.0,0.2\n"
    df = read_csv_with_header_sniff(data, ["agg_trade_id", "price", "quantity"])
    assert len(df) == 2
    assert list(df.columns) == ["agg_trade_id", "price", "quantity"]
    assert df["agg_trade_id"].tolist() == [1, 2]


def test_read_csv_with_header_sniff_keeps_all_rows_when_headerless():
    """旧格式无 header（首列是整数 id），一行都不能丢。"""
    data = b"1,100.0,0.1\n2,101.0,0.2\n"
    df = read_csv_with_header_sniff(data, ["agg_trade_id", "price", "quantity"])
    assert len(df) == 2
    assert df["price"].tolist() == [100.0, 101.0]
