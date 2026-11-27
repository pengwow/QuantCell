"""DataIntegrityChecker parquet 检查口径自检

检查口径必须与回测读取口径是同一物理文件（source 单文件 Parquet），
否则会出现"下载完成（写到别处）但检查仍报不完整"。
"""

from datetime import datetime, timedelta

import pandas as pd

from backtest.data_integrity import DataIntegrityChecker


def _write_source_parquet(tmp_path, rows_ns, market="spot", symbol="ETHUSDT", interval="1h"):
    file_path = tmp_path / "crypto" / market / "klines" / interval / f"{symbol}.parquet"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        {
            "timestamp": rows_ns,
            "open": 1.0,
            "high": 1.0,
            "low": 1.0,
            "close": 1.0,
            "volume": 1.0,
        }
    ).to_parquet(file_path, index=False)


def _ns(dt: datetime) -> int:
    return int(dt.timestamp() * 1_000_000_000)


def test_parquet_source_detects_hole(tmp_path, monkeypatch):
    monkeypatch.setattr("utils.data_utils.get_source_data_dir", lambda: tmp_path)
    checker = DataIntegrityChecker()

    base = datetime(2026, 5, 1, 0, 0)
    end = base + timedelta(hours=5)
    # 6 根网格缺 2~3 两根
    _write_source_parquet(tmp_path, [_ns(base + timedelta(hours=h)) for h in (0, 1, 4, 5)])

    result = checker.check_data_completeness("ETHUSDT", "1h", base, end, source="parquet")

    assert not result.is_complete
    assert result.missing_count == 2
    assert result.missing_ranges == [(datetime(2026, 5, 1, 2, 0), datetime(2026, 5, 1, 3, 0))]


def test_parquet_source_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr("utils.data_utils.get_source_data_dir", lambda: tmp_path)
    checker = DataIntegrityChecker()

    base = datetime(2026, 5, 1, 0, 0)
    end = base + timedelta(hours=5)
    result = checker.check_data_completeness("ETHUSDT", "1h", base, end, source="parquet")

    assert not result.is_complete
    assert result.missing_ranges == [(base, end)]


def test_parquet_source_complete(tmp_path, monkeypatch):
    monkeypatch.setattr("utils.data_utils.get_source_data_dir", lambda: tmp_path)
    checker = DataIntegrityChecker()

    base = datetime(2026, 5, 1, 0, 0)
    end = base + timedelta(hours=5)
    _write_source_parquet(tmp_path, [_ns(base + timedelta(hours=h)) for h in range(6)])

    result = checker.check_data_completeness("ETHUSDT", "1h", base, end, source="parquet")

    assert result.is_complete
    assert result.coverage_percent == 100.0


def test_parquet_um_maps_to_future_dir(tmp_path, monkeypatch):
    """crypto_type=um/cm 的数据存放在 future 目录（单数）"""
    monkeypatch.setattr("utils.data_utils.get_source_data_dir", lambda: tmp_path)
    checker = DataIntegrityChecker()

    base = datetime(2026, 5, 1, 0, 0)
    end = base + timedelta(hours=5)
    _write_source_parquet(tmp_path, [_ns(base + timedelta(hours=h)) for h in range(6)], market="future")

    result = checker.check_data_completeness("ETHUSDT", "1h", base, end, crypto_type="um", source="parquet")

    assert result.is_complete
