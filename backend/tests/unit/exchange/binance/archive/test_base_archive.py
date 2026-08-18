"""Tests for BaseBinanceArchiveDownloader shared base class."""

from datetime import date
from typing import TYPE_CHECKING

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
