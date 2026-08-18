"""Tests for archive kinds enum + URL builder."""

from exchange.binance.archive.kinds import (
    KIND_INTERVALS,
    ArchiveKind,
    MarketType,
    build_zip_url,
    get_save_dir,
)


def test_archive_kind_enum_has_7_values():
    assert len(ArchiveKind) == 7
    assert ArchiveKind.AGG_TRADES.value == "aggTrades"
    assert ArchiveKind.TRADES.value == "trades"
    assert ArchiveKind.BOOK_DEPTH.value == "bookDepth"
    assert ArchiveKind.BOOK_TICKER.value == "bookTicker"
    assert ArchiveKind.MARK_KLINES.value == "markPriceKlines"
    assert ArchiveKind.INDEX_KLINES.value == "indexPriceKlines"
    assert ArchiveKind.PREMIUM_KLINES.value == "premiumIndexKlines"


def test_market_type_enum_has_3_values():
    assert len(MarketType) == 3
    assert MarketType.SPOT.value == "spot"
    assert MarketType.FUTURES_UM.value == "um"
    assert MarketType.FUTURES_CM.value == "cm"


def test_kinds_that_need_interval():
    assert KIND_INTERVALS[ArchiveKind.MARK_KLINES] == [
        "1m",
        "3m",
        "5m",
        "15m",
        "30m",
        "1h",
        "2h",
        "1d",
    ]
    assert KIND_INTERVALS[ArchiveKind.INDEX_KLINES] == [
        "1m",
        "3m",
        "5m",
        "15m",
        "30m",
        "1h",
        "2h",
        "1d",
    ]
    assert KIND_INTERVALS[ArchiveKind.PREMIUM_KLINES] == [
        "1m",
        "3m",
        "5m",
        "15m",
        "30m",
        "1h",
        "2h",
        "1d",
    ]
    assert KIND_INTERVALS[ArchiveKind.AGG_TRADES] is None
    assert KIND_INTERVALS[ArchiveKind.TRADES] is None
    assert KIND_INTERVALS[ArchiveKind.BOOK_DEPTH] is None
    assert KIND_INTERVALS[ArchiveKind.BOOK_TICKER] is None


def test_build_zip_url_spot_aggtrades():
    url = build_zip_url(MarketType.SPOT, ArchiveKind.AGG_TRADES, "BTCUSDT", "2024-12-01")
    assert url == "https://data.binance.vision/data/spot/daily/aggTrades/BTCUSDT/BTCUSDT-aggTrades-2024-12-01.zip"


def test_build_zip_url_um_mark_klines_with_interval():
    url = build_zip_url(
        MarketType.FUTURES_UM,
        ArchiveKind.MARK_KLINES,
        "BTCUSDT",
        "2024-12-01",
        interval="1h",
    )
    assert (
        url
        == "https://data.binance.vision/data/futures/um/daily/markPriceKlines/BTCUSDT/1h/BTCUSDT-markPriceKlines-1h-2024-12-01.zip"
    )


def test_build_zip_url_cm_book_depth():
    url = build_zip_url(MarketType.FUTURES_CM, ArchiveKind.BOOK_DEPTH, "BTCUSD", "2024-12-01")
    assert url == "https://data.binance.vision/data/futures/cm/daily/bookDepth/BTCUSD/BTCUSD-bookDepth-2024-12-01.zip"


def test_get_save_dir_spot():
    base = "/tmp/qc"
    d = get_save_dir(base, MarketType.SPOT, ArchiveKind.AGG_TRADES, "BTCUSDT")
    assert str(d) == "/tmp/qc/spot/aggTrades/BTCUSDT"
