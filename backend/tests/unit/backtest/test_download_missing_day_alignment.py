"""_download_missing_data 下载段天对齐自检

binance vision 逐日 zip 语义：起止必须对齐整天，半天的缺口也要下载完整一天
（此前 ±1h 缓冲导致跨天段拿到不完整的一天）。
"""

from datetime import datetime

from backtest.data_downloader import BacktestDataDownloader


def _make_downloader(monkeypatch, calls: list) -> BacktestDataDownloader:
    # 绕过 __init__：它会实例化 DataService/StandaloneDataDownloader，测试不需要
    downloader = BacktestDataDownloader.__new__(BacktestDataDownloader)
    downloader.standalone_mode = True
    downloader.standalone_downloader = object()

    def fake_standalone(**kwargs):
        calls.append(kwargs)
        return True

    monkeypatch.setattr(downloader, "_download_with_standalone", fake_standalone)
    return downloader


def test_intraday_segment_aligned_to_days(monkeypatch):
    calls: list = []
    downloader = _make_downloader(monkeypatch, calls)

    ok = downloader._download_missing_data(
        symbol="ETHUSDT",
        interval="15m",
        missing_ranges=[(datetime(2026, 5, 1, 13, 0), datetime(2026, 5, 1, 15, 30))],
        market_type="crypto",
        crypto_type="um",
        max_wait_time=10,
    )

    assert ok
    assert calls[0]["earliest_start"] == datetime(2026, 5, 1, 0, 0)
    assert calls[0]["latest_end"] == datetime(2026, 5, 2, 0, 0)
    assert calls[0]["crypto_type"] == "um"


def test_full_day_end_not_extended(monkeypatch):
    """end_time 恰好是整天 00:00 时不再多加一天"""
    calls: list = []
    downloader = _make_downloader(monkeypatch, calls)

    downloader._download_missing_data(
        symbol="ETHUSDT",
        interval="1h",
        missing_ranges=[(datetime(2026, 5, 1, 0, 0), datetime(2026, 5, 2, 0, 0))],
        market_type="crypto",
        crypto_type="spot",
        max_wait_time=10,
    )

    assert calls[0]["earliest_start"] == datetime(2026, 5, 1, 0, 0)
    assert calls[0]["latest_end"] == datetime(2026, 5, 2, 0, 0)


def test_empty_missing_ranges_noop(monkeypatch):
    calls: list = []
    downloader = _make_downloader(monkeypatch, calls)

    assert downloader._download_missing_data(
        symbol="ETHUSDT",
        interval="1h",
        missing_ranges=[],
        market_type="crypto",
        crypto_type="spot",
        max_wait_time=10,
    )
    assert calls == []
