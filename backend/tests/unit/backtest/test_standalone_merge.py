"""_merge_to_source_parquet 自检：毫秒→纳秒换算、目录口径、幂等去重"""

from datetime import datetime

import pandas as pd

import backtest.standalone_downloader as sd
from backtest.standalone_downloader import StandaloneDataDownloader


def _df_ms(open_ms: list[int]) -> pd.DataFrame:
    n = len(open_ms)
    return pd.DataFrame(
        {
            "open_time": open_ms,
            "open": [1.0] * n,
            "high": [2.0] * n,
            "low": [0.5] * n,
            "close": [1.5] * n,
            "volume": [10.0] * n,
        }
    )


def test_merge_writes_nanoseconds_to_future_dir(tmp_path, monkeypatch):
    monkeypatch.setattr("utils.data_utils.get_source_data_dir", lambda: tmp_path)
    downloader = StandaloneDataDownloader()

    open_ms = int(datetime(2026, 5, 1, 0, 0).timestamp() * 1000)
    ok = downloader._merge_to_source_parquet(_df_ms([open_ms]), "ETHUSDT", "15m", "um")

    assert ok
    expected = tmp_path / "crypto" / "future" / "klines" / "15m" / "ETHUSDT.parquet"
    assert expected.exists()
    out = pd.read_parquet(expected)
    assert out["timestamp"].iloc[0] == open_ms * 1_000_000
    assert set(out.columns) == {"timestamp", "open", "high", "low", "close", "volume", "symbol"}
    assert out["symbol"].iloc[0] == "ETHUSDT"


def test_merge_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr("utils.data_utils.get_source_data_dir", lambda: tmp_path)
    downloader = StandaloneDataDownloader()

    open_ms = int(datetime(2026, 5, 1, 0, 0).timestamp() * 1000)
    downloader._merge_to_source_parquet(_df_ms([open_ms]), "ETHUSDT", "15m", "spot")
    downloader._merge_to_source_parquet(_df_ms([open_ms]), "ETHUSDT", "15m", "spot")

    out = pd.read_parquet(tmp_path / "crypto" / "spot" / "klines" / "15m" / "ETHUSDT.parquet")
    assert len(out) == 1


def test_merger_lock_reused_per_key():
    """同 key 返回同一把锁（进程内互斥的基本保证）"""
    with sd._merge_locks_guard:
        for k in list(sd._merge_locks):
            del sd._merge_locks[k]
    a = sd._merge_lock("ETHUSDT_15m_future")
    b = sd._merge_lock("ETHUSDT_15m_future")
    c = sd._merge_lock("BTCUSDT_1h_spot")
    assert a is b
    assert a is not c
