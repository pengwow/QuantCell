"""_calculate_missing_ranges 纳秒口径自检

历史 bug：DB 现有数据 timestamp 是纳秒整型（P2-14 BIGINT），而满量程网格
被换算成毫秒（ts.timestamp() * 1000），两侧集合永不相交 → missing_ranges
恒等于全量，"下载完成后仍认为缺全部数据"。
"""

from datetime import datetime, timedelta

import pandas as pd

from backtest.data_integrity import DataIntegrityChecker


def _ns(dt: datetime) -> int:
    return int(dt.timestamp() * 1_000_000_000)


def test_missing_ranges_with_nanosecond_timestamps():
    checker = DataIntegrityChecker()
    base = datetime(2026, 5, 1, 0, 0)
    end = base + timedelta(hours=5)
    # 1h 网格 0~5 点共 6 根，现有数据缺 2~3 点两根；timestamp 为纳秒（DB 口径）
    ns = [_ns(base + timedelta(hours=h)) for h in (0, 1, 4, 5)]
    existing = pd.DataFrame({"timestamp": ns, "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0})

    ranges = checker._calculate_missing_ranges(existing, base, end, "1h")

    assert ranges == [(datetime(2026, 5, 1, 2, 0), datetime(2026, 5, 1, 3, 0))]


def test_missing_ranges_full_data_returns_empty():
    checker = DataIntegrityChecker()
    base = datetime(2026, 5, 1, 0, 0)
    end = base + timedelta(hours=5)
    ns = [_ns(base + timedelta(hours=h)) for h in range(6)]
    existing = pd.DataFrame({"timestamp": ns, "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0})

    assert checker._calculate_missing_ranges(existing, base, end, "1h") == []


def test_missing_ranges_empty_returns_full_range():
    checker = DataIntegrityChecker()
    base = datetime(2026, 5, 1, 0, 0)
    end = base + timedelta(hours=5)
    empty = pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    assert checker._calculate_missing_ranges(empty, base, end, "1h") == [(base, end)]
