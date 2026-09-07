"""collector.services.data_collector 单元测试。

覆盖数据采集门面层：
- _candle_type_from_market / _market_type_from_str 工具函数
- KlineCollector.collect: 委托 BinanceDownloader，symbol×interval 双重循环
- ArchiveCollector.collect: 委托 BinanceArchiveFactory
- DataCollector.collect: 按 data_type 路由 + 未知类型报错
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from collector.services.data_collector import (
    ArchiveCollector,
    DataCollector,
    KlineCollector,
    _candle_type_from_market,
    _market_type_from_str,
)
from exchange.binance.archive.kinds import MarketType

# =================== 工具函数 ===================


def test_candle_type_from_market():
    assert _candle_type_from_market("spot") == "spot"
    assert _candle_type_from_market("um") == "futures"
    assert _candle_type_from_market("cm") == "futures"


def test_market_type_from_str():
    assert _market_type_from_str("spot") == MarketType.SPOT
    assert _market_type_from_str("um") == MarketType.FUTURES_UM
    assert _market_type_from_str("cm") == MarketType.FUTURES_CM
    with pytest.raises(KeyError):
        _market_type_from_str("unknown")


# =================== KlineCollector ===================


class TestKlineCollector:
    def test_collect_delegates_to_binance_downloader(self, tmp_path):
        with patch("collector.services.data_collector.BinanceDownloader") as MockDownloader:
            inst = MockDownloader.return_value
            collector = KlineCollector(base_dir=str(tmp_path))
            collector.collect(
                data_type="kline",
                market="spot",
                symbols=["BTCUSDT", "ETHUSDT"],
                intervals=["1h", "4h"],
                start="2024-01-01",
                end="2024-01-02",
                max_workers=2,
                mode="full",
            )
        # symbol × interval 共 4 次下载
        assert MockDownloader.call_count == 4
        calls = MockDownloader.call_args_list
        assert str(tmp_path) in calls[0].kwargs["save_dir"]
        assert "kline" in calls[0].kwargs["save_dir"]
        assert "spot" in calls[0].kwargs["save_dir"]
        assert calls[0].kwargs["candle_type"] == "spot"
        assert calls[0].kwargs["symbols"] == ["BTCUSDT"]
        assert calls[0].kwargs["max_workers"] == 2
        assert calls[0].kwargs["mode"] == "full"
        assert inst.collect_data.call_count == 4


# =================== ArchiveCollector ===================


class TestArchiveCollector:
    def test_collect_delegates_to_archive_factory(self, tmp_path):
        with patch("collector.services.data_collector.BinanceArchiveFactory") as MockFactory:
            factory = MockFactory.return_value
            downloader = MagicMock()
            factory.create.return_value = downloader

            collector = ArchiveCollector(base_dir=str(tmp_path))
            collector.collect(
                data_type="aggTrades",
                market="um",
                symbols=["BTCUSDT"],
                intervals=["1h"],
                start="2024-01-01",
                end="2024-01-02",
            )

            factory.create.assert_called_once()
            kwargs = factory.create.call_args.kwargs
            assert kwargs["kind"] == "aggTrades"
            assert kwargs["market"] == MarketType.FUTURES_UM
            assert kwargs["symbol"] == "BTCUSDT"
            assert kwargs["interval"] == "1h"
            downloader.collect_data.assert_called_once_with(symbols=["BTCUSDT"], start="2024-01-01", end="2024-01-02")

    def test_collect_defaults_when_no_interval_or_dates(self, tmp_path):
        with patch("collector.services.data_collector.BinanceArchiveFactory") as MockFactory:
            downloader = MagicMock()
            MockFactory.return_value.create.return_value = downloader
            collector = ArchiveCollector(base_dir=str(tmp_path))
            collector.collect(data_type="trades", market="um", symbols=["BTCUSDT"])
            kwargs = MockFactory.return_value.create.call_args.kwargs
            assert kwargs["interval"] is None
            downloader.collect_data.assert_called_once_with(symbols=["BTCUSDT"], start="2024-01-01", end="2025-12-31")


# =================== DataCollector 路由 ===================


class TestDataCollector:
    def test_route_unknown_type_raises(self):
        with pytest.raises(ValueError, match="未知的数据类型"):
            DataCollector("/tmp").collect("bogus", "spot", ["BTCUSDT"])

    def test_route_kline(self):
        with patch("collector.services.data_collector.KlineCollector") as M:
            DataCollector("/tmp/base").collect(
                data_type="kline", market="um", symbols=["BTCUSDT"], intervals=["1h"], start="2024-01-01"
            )
            collector_inst = M.return_value
            collector_inst.collect.assert_called_once()
            kwargs = collector_inst.collect.call_args.kwargs
            assert kwargs["data_type"] == "kline"
            assert kwargs["market"] == "um"
            assert kwargs["symbols"] == ["BTCUSDT"]
            assert kwargs["intervals"] == ["1h"]

    def test_route_archive(self):
        with patch("collector.services.data_collector.ArchiveCollector") as M:
            DataCollector("/tmp/base").collect(
                data_type="aggTrades", market="um", symbols=["BTCUSDT"], start="2024-01-01"
            )
            M.return_value.collect.assert_called_once()

    def test_route_deriv(self):
        with patch("collector.services.deriv_collector.DerivCollector") as M:
            DataCollector("/tmp/base").collect(
                data_type="fundingRate", market="um", symbols=["BTCUSDT"], start="2024-01-01"
            )
            M.return_value.collect.assert_called_once()
            kwargs = M.return_value.collect.call_args.kwargs
            assert kwargs["data_type"] == "fundingRate"
            assert kwargs["symbols"] == ["BTCUSDT"]

    def test_open_interest_routes_to_deriv(self):
        with patch("collector.services.deriv_collector.DerivCollector") as M:
            DataCollector("/tmp/base").collect(data_type="openInterest", market="um", symbols=["BTCUSDT"])
            M.return_value.collect.assert_called_once()
