"""Tests for BinanceArchiveFactory: 7 kinds × 3 markets = 21 combinations."""

from __future__ import annotations

from pathlib import Path

import pytest

from exchange.binance.archive.factory import BinanceArchiveFactory
from exchange.binance.archive.fetchers.agg_trades import AggTradesFetcher
from exchange.binance.archive.fetchers.book_depth import BookDepthFetcher
from exchange.binance.archive.fetchers.book_ticker import BookTickerFetcher
from exchange.binance.archive.fetchers.index_price_klines import IndexPriceKlinesFetcher
from exchange.binance.archive.fetchers.mark_price_klines import MarkPriceKlinesFetcher
from exchange.binance.archive.fetchers.premium_index_klines import (
    PremiumIndexKlinesFetcher,
)
from exchange.binance.archive.fetchers.trades import TradesFetcher
from exchange.binance.archive.kinds import ArchiveKind, MarketType

# ——— kind → fetcher 类映射（21 组合的断言依据）——
_KIND_TO_FETCHER = {
    ArchiveKind.AGG_TRADES: AggTradesFetcher,
    ArchiveKind.TRADES: TradesFetcher,
    ArchiveKind.BOOK_DEPTH: BookDepthFetcher,
    ArchiveKind.BOOK_TICKER: BookTickerFetcher,
    ArchiveKind.MARK_KLINES: MarkPriceKlinesFetcher,
    ArchiveKind.INDEX_KLINES: IndexPriceKlinesFetcher,
    ArchiveKind.PREMIUM_KLINES: PremiumIndexKlinesFetcher,
}


def test_create_returns_agg_trades_fetcher(tmp_path: Path):
    f = BinanceArchiveFactory.create(ArchiveKind.AGG_TRADES, MarketType.SPOT, base_dir=tmp_path, symbol="BTCUSDT")
    assert isinstance(f, AggTradesFetcher)
    assert f.market == MarketType.SPOT
    assert f.archive_kind == ArchiveKind.AGG_TRADES


def test_create_returns_trades_fetcher(tmp_path: Path):
    f = BinanceArchiveFactory.create(ArchiveKind.TRADES, MarketType.SPOT, base_dir=tmp_path, symbol="BTCUSDT")
    assert isinstance(f, TradesFetcher)
    assert f.archive_kind == ArchiveKind.TRADES


def test_create_returns_book_ticker_fetcher(tmp_path: Path):
    f = BinanceArchiveFactory.create(
        ArchiveKind.BOOK_TICKER,
        MarketType.FUTURES_UM,
        base_dir=tmp_path,
        symbol="BTCUSDT",
    )
    assert isinstance(f, BookTickerFetcher)
    assert f.market == MarketType.FUTURES_UM


def test_create_returns_book_depth_fetcher(tmp_path: Path):
    f = BinanceArchiveFactory.create(
        ArchiveKind.BOOK_DEPTH,
        MarketType.FUTURES_CM,
        base_dir=tmp_path,
        symbol="BTCUSD",
    )
    assert isinstance(f, BookDepthFetcher)
    assert f.market == MarketType.FUTURES_CM


def test_create_returns_mark_klines_fetcher(tmp_path: Path):
    f = BinanceArchiveFactory.create(ArchiveKind.MARK_KLINES, MarketType.SPOT, base_dir=tmp_path, symbol="BTCUSDT")
    assert isinstance(f, MarkPriceKlinesFetcher)


def test_create_returns_index_klines_fetcher(tmp_path: Path):
    f = BinanceArchiveFactory.create(
        ArchiveKind.INDEX_KLINES,
        MarketType.FUTURES_UM,
        base_dir=tmp_path,
        symbol="BTCUSDT",
    )
    assert isinstance(f, IndexPriceKlinesFetcher)


def test_create_returns_premium_klines_fetcher(tmp_path: Path):
    f = BinanceArchiveFactory.create(ArchiveKind.PREMIUM_KLINES, MarketType.SPOT, base_dir=tmp_path, symbol="BTCUSDT")
    assert isinstance(f, PremiumIndexKlinesFetcher)


def test_all_21_combinations_return_non_none_instance(tmp_path: Path):
    """7 kinds × 3 markets = 21 组合全部应返回非 None fetcher 实例。"""
    for kind in ArchiveKind:
        for market in MarketType:
            f = BinanceArchiveFactory.create(kind, market, base_dir=tmp_path, symbol="BTCUSDT")
            assert f is not None, f"Got None for {kind}/{market}"
            assert isinstance(f, _KIND_TO_FETCHER[kind]), f"Wrong class for {kind}/{market}: got {type(f).__name__}"
            assert f.market == market
            assert f.archive_kind == kind


def test_21_combinations_count():
    """穷举确认枚举规模：7 × 3 = 21。"""
    assert len(ArchiveKind) * len(MarketType) == 21


def test_arguments_passed_through(tmp_path: Path):
    """market / base_dir / symbol 必须透传到 fetcher 实例。"""
    f = BinanceArchiveFactory.create(
        ArchiveKind.AGG_TRADES,
        MarketType.FUTURES_UM,
        base_dir=tmp_path,
        symbol="ETHUSDT",
    )
    assert f.market == MarketType.FUTURES_UM
    assert f.base_dir == Path(tmp_path)
    assert f.save_dir == Path(tmp_path) / "um" / "aggTrades" / "ETHUSDT"


def test_interval_passed_through_to_klines_fetcher(tmp_path: Path):
    """K 线 fetcher 接收 interval 参数。"""
    f = BinanceArchiveFactory.create(
        ArchiveKind.MARK_KLINES,
        MarketType.SPOT,
        base_dir=tmp_path,
        symbol="BTCUSDT",
        interval="1h",
    )
    assert f.interval == "1h"


def test_proxy_passed_through(tmp_path: Path):
    """proxy 参数透传。"""
    f = BinanceArchiveFactory.create(
        ArchiveKind.TRADES,
        MarketType.SPOT,
        base_dir=tmp_path,
        symbol="BTCUSDT",
        proxy="http://127.0.0.1:7890",
    )
    assert f.proxy == "http://127.0.0.1:7890"


def test_unknown_kind_string_raises_value_error(tmp_path: Path):
    """不存在的 kind 字符串应抛 ValueError。"""
    with pytest.raises(ValueError):
        BinanceArchiveFactory.create("not_a_kind", MarketType.SPOT, base_dir=tmp_path, symbol="BTCUSDT")


def test_valid_kind_string_also_accepted(tmp_path: Path):
    """工厂同时接受 enum 实例和其对应 value 字符串。"""
    f = BinanceArchiveFactory.create("aggTrades", MarketType.SPOT, base_dir=tmp_path, symbol="BTCUSDT")
    assert isinstance(f, AggTradesFetcher)


def test_each_fetcher_has_required_hooks(tmp_path: Path):
    """每个 fetcher 必须有 4 个钩子类属性：archive_kind / url_subpath / column_mapping / parquet_schema。"""
    for kind in ArchiveKind:
        f = BinanceArchiveFactory.create(kind, MarketType.SPOT, base_dir=tmp_path, symbol="BTCUSDT")
        assert f.archive_kind == kind
        assert isinstance(f.url_subpath, str) and f.url_subpath
        assert isinstance(f.column_mapping, dict)
