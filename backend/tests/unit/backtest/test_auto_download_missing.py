"""回测启动前 kline 缺失数据自动补齐（BacktestService._ensure_kline_data）"""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from backtest.service import BacktestService


def _task(**config):
    base = {
        "data_type": "kline",
        "market": "spot",
        "start_time": "2026-04-30 00:00:00",
        "end_time": "2026-05-02 00:00:00",
    }
    base.update(config)
    return {"symbols": ["BTCUSDT"], "timeframes": ["1h"], "config": base}


@pytest.fixture
def svc():
    return BacktestService()


@pytest.fixture
def downloader(monkeypatch):
    instance = MagicMock()
    instance.ensure_data_complete.return_value = (True, MagicMock(coverage_percent=100.0))
    monkeypatch.setattr("backtest.data_downloader.BacktestDataDownloader", lambda: instance)
    return instance


def test_non_kline_skips_download(svc, downloader):
    svc._ensure_kline_data("t1", _task(data_type="aggTrades"))
    downloader.ensure_data_complete.assert_not_called()


def test_missing_time_range_skips_download(svc, downloader):
    svc._ensure_kline_data("t1", _task(start_time=None))
    downloader.ensure_data_complete.assert_not_called()


def test_kline_missing_triggers_download(svc, downloader):
    svc._ensure_kline_data("t1", _task(market="um"))
    kwargs = downloader.ensure_data_complete.call_args.kwargs
    assert kwargs["symbol"] == "BTCUSDT"
    assert kwargs["interval"] == "1h"
    assert kwargs["crypto_type"] == "um"
    assert kwargs["start_time"] == datetime(2026, 4, 30)
    assert kwargs["end_time"] == datetime(2026, 5, 2)


def test_download_failure_does_not_raise(svc, downloader):
    downloader.ensure_data_complete.side_effect = RuntimeError("network down")
    svc._ensure_kline_data("t1", _task())  # 不抛异常即通过：交由引擎数据加载口径收尾
