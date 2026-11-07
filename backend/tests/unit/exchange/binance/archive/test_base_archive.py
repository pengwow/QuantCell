"""Tests for BaseBinanceArchiveDownloader shared base class."""

from datetime import date
from typing import TYPE_CHECKING

import pytest

from exchange.binance.archive.base import BaseBinanceArchiveDownloader
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
