"""quality.kline_quality_service 单元测试。

使用 FakeProvider 实现 DataProvider 抽象接口，不触碰真实数据源。

覆盖：
- check_quality（error / empty / 正常路径）
- check_integrity / check_continuity / check_validity / check_uniqueness
- resolve_duplicates（dry_run 及各策略分支）
- _get_time_range / _analyze_gaps / _calculate_summary
"""

from __future__ import annotations

import pandas as pd
import pytest

from quality.kline_quality_service import KlineQualityService

# 2024-01-01 00:00:00 UTC 的纳秒时间戳
TS_BASE = 1_704_067_200_000_000_000
MINUTE_NS = 60_000_000_000


class FakeProvider:
    """内存版 DataProvider，可注入返回数据或抛异常。"""

    def __init__(self, df: pd.DataFrame | None = None):
        self._df = df
        self.raises: Exception | None = None

    def get_kline_data(self, symbol, interval, candle_type="spot", start=None, end=None):
        if self.raises:
            raise self.raises
        return self._df

    def list_symbols(self, candle_type="spot") -> list:
        return []

    def list_intervals(self, symbol, candle_type="spot") -> list:
        return []


def _base_row(minutes: int = 0, **kwargs) -> dict:
    row = {
        "timestamp": TS_BASE + minutes * MINUTE_NS,
        "open": 100.0,
        "high": 102.0,
        "low": 98.0,
        "close": 101.0,
        "volume": 1000.0,
    }
    row.update(kwargs)
    return row


def _service_from_df(df: pd.DataFrame) -> tuple[KlineQualityService, FakeProvider]:
    provider = FakeProvider(df)
    return KlineQualityService(provider), provider


# ==================== check_quality ====================


def test_check_quality_error_returns_error_report():
    provider = FakeProvider()
    provider.raises = FileNotFoundError("no file")
    service = KlineQualityService(provider)

    result = service.check_quality("BTCUSDT", "1h", start="2024-01-01", end="2024-01-02")

    assert result["status"] == "error"
    assert result["symbol"] == "BTCUSDT"
    assert result["message"] == "no file"
    assert result["summary"] == {}


def test_check_quality_empty_df_returns_empty_status():
    service, _ = _service_from_df(pd.DataFrame())
    result = service.check_quality("BTCUSDT", "1h")
    assert result["status"] == "empty"
    assert result["total_records"] == 0


def test_check_quality_full_report():
    df = pd.DataFrame([_base_row(minutes=i) for i in range(3)])
    service, _ = _service_from_df(df)

    result = service.check_quality("BTCUSDT", "1h")

    assert result["total_records"] == 3
    assert result["details"]["integrity"]["status"] == "pass"
    assert result["details"]["continuity"]["status"] == "pass"
    assert result["details"]["validity"]["status"] == "pass"
    assert result["details"]["uniqueness"]["status"] == "pass"
    assert result["summary"]["checks_passed"] == 4
    assert result["summary"]["score"] == 100.0
    assert result["summary"]["grade"] == "A"


# ==================== check_integrity ====================


def test_check_integrity_missing_column():
    df = _base_row(0)
    # 去掉 volume 列
    df = pd.DataFrame([df]).drop(columns=["volume"])
    service = KlineQualityService(FakeProvider())

    result = service.check_integrity(df)

    assert result["status"] == "fail"
    assert result["missing_columns"] == ["volume"]


def test_check_integrity_missing_values():
    df = pd.DataFrame([_base_row(0)])
    # 显式构造 NaN
    df.loc[0, "close"] = None
    df.loc[0, "volume"] = None
    service = KlineQualityService(FakeProvider())

    result = service.check_integrity(df)

    assert result["status"] == "fail"
    assert result["missing_values"] == {"close": 1, "volume": 1}


def test_check_integrity_pass():
    df = pd.DataFrame([_base_row(0)])
    service = KlineQualityService(FakeProvider())
    result = service.check_integrity(df)
    assert result["status"] == "pass"
    assert result["missing_columns"] == []


# ==================== check_continuity ====================


def _continuous_1m_df(count: int, gap_minutes: list[int] | None = None) -> pd.DataFrame:
    """生成 1m 数据，可指定缺失的分钟下标。"""
    gap_set = set(gap_minutes or [])
    minutes = [i for i in range(count) if i not in gap_set]
    return pd.DataFrame(
        {
            "timestamp": [TS_BASE + m * MINUTE_NS for m in minutes],
            "open": [100.0] * len(minutes),
            "high": [102.0] * len(minutes),
            "low": [98.0] * len(minutes),
            "close": [101.0] * len(minutes),
            "volume": [1000.0] * len(minutes),
        }
    )


def test_continuity_has_gap_fails():
    df = _continuous_1m_df(4, gap_minutes=[2])  # 00:00,00:01,00:03
    service = KlineQualityService(FakeProvider())

    result = service.check_continuity(df, "1m")

    assert result["status"] == "fail"
    assert result["missing_records"] == 1
    assert result["expected_records"] == 4
    assert result["coverage_ratio"] == 0.75
    assert len(result["gaps"]) >= 1


def test_continuity_no_gap_passes():
    df = _continuous_1m_df(3)
    service = KlineQualityService(FakeProvider())

    result = service.check_continuity(df, "1m")

    assert result["status"] == "pass"
    assert result["missing_records"] == 0
    assert result["expected_records"] == 3
    assert result["coverage_ratio"] == 1.0


def test_continuity_unsupported_interval_returns_pass():
    df = _continuous_1m_df(3)
    service = KlineQualityService(FakeProvider())

    result = service.check_continuity(df, "xyz")

    assert result["status"] == "pass"
    assert result["expected_records"] == 0


# ==================== check_validity ====================


def test_check_validity_negative_price():
    df = pd.DataFrame([_base_row(0, close=-1.0)])
    service = KlineQualityService(FakeProvider())

    result = service.check_validity(df)

    assert result["status"] == "fail"
    assert result["issues"]["negative_prices"] == 1


def test_check_validity_negative_volume_and_bad_hl():
    df = pd.DataFrame(
        [
            _base_row(0, **{"volume": -10.0}),
            _base_row(1, **{"high": 99.0, "low": 101.0}),
        ]
    )
    service = KlineQualityService(FakeProvider())

    result = service.check_validity(df)

    assert result["status"] == "fail"
    assert result["issues"]["negative_volumes"] == 1
    assert result["issues"]["invalid_high_low"] == 1


def test_check_validity_abnormal_change():
    df = pd.DataFrame(
        [
            _base_row(0, **{"open": 100.0, "close": 100.0}),
            _base_row(1, **{"open": 200.0, "close": 300.0}),  # +200%
        ]
    )
    service = KlineQualityService(FakeProvider())

    result = service.check_validity(df)

    assert result["status"] == "fail"
    assert result["issues"]["abnormal_changes"] == 1
    assert result["issue_details"][-1]["max_change"] >= 200.0


def test_check_validity_pass():
    df = pd.DataFrame([_base_row(0), _base_row(1, close=101.5)])
    service = KlineQualityService(FakeProvider())
    result = service.check_validity(df)
    assert result["status"] == "pass"
    assert result["issues"]["negative_prices"] == 0


# ==================== check_uniqueness ====================


def test_check_uniqueness_duplicates():
    df = pd.DataFrame(
        [
            _base_row(0),
            _base_row(0),
            _base_row(1),
        ]
    )
    service = KlineQualityService(FakeProvider())

    result = service.check_uniqueness(df)

    assert result["status"] == "fail"
    assert result["duplicate_count"] == 2


def test_check_uniqueness_no_duplicates():
    df = pd.DataFrame([_base_row(0), _base_row(1)])
    service = KlineQualityService(FakeProvider())
    result = service.check_uniqueness(df)
    assert result["status"] == "pass"
    assert result["duplicate_count"] == 0


# ==================== resolve_duplicates ====================


def test_resolve_duplicates_no_duplicates():
    df = pd.DataFrame([_base_row(0), _base_row(1)])
    service, _ = _service_from_df(df)

    result = service.resolve_duplicates("BTCUSDT", "1m", strategy="keep_first")

    assert result["status"] == "success"
    assert result["processed_count"] == 0


def test_resolve_duplicates_dry_run_keep_first():
    df = pd.DataFrame([_base_row(0), _base_row(0), _base_row(1)])
    service, _ = _service_from_df(df)

    result = service.resolve_duplicates("BTCUSDT", "1m", strategy="keep_first", dry_run=True)

    assert result["status"] == "preview"
    assert result["original_count"] == 3
    assert result["remaining_count"] == 2
    assert result["removed_count"] == 1


def test_resolve_duplicates_dry_run_keep_max_volume():
    df = pd.DataFrame(
        [
            _base_row(0, **{"volume": 10.0}),
            _base_row(0, **{"volume": 100.0}),
            _base_row(1, **{"volume": 50.0}),
        ]
    )
    service, _ = _service_from_df(df)

    result = service.resolve_duplicates("BTCUSDT", "1m", strategy="keep_max_volume", dry_run=True)

    assert result["status"] == "preview"
    assert result["removed_count"] == 1


def test_resolve_duplicates_unsupported_strategy():
    df = pd.DataFrame([_base_row(0), _base_row(0)])
    service, _ = _service_from_df(df)

    result = service.resolve_duplicates("BTCUSDT", "1m", strategy="invalid")

    assert result["status"] == "error"
    assert "不支持的处理策略" in result["message"]


def test_resolve_duplicates_empty_df_warns():
    service, _ = _service_from_df(pd.DataFrame())

    result = service.resolve_duplicates("BTCUSDT", "1m", strategy="keep_first")

    assert result["status"] == "warning"


# ==================== 内部方法 ====================


def test_get_time_range_various_precisions():
    service = KlineQualityService(FakeProvider())

    ns_df = pd.DataFrame({"timestamp": [TS_BASE, TS_BASE + MINUTE_NS * 5]})
    r1 = service._get_time_range(ns_df)
    assert r1["start"].startswith("2024-01-01")
    assert r1["end"].startswith("2024-01-01")
    assert ":" in r1["start"]

    sec_df = pd.DataFrame({"timestamp": [1704067200, 1704067500]})
    r3 = service._get_time_range(sec_df)
    assert r3["start"].startswith("2024-01-01")


def test_get_time_range_empty_df():
    service = KlineQualityService(FakeProvider())
    assert service._get_time_range(pd.DataFrame()) == {"start": "-", "end": "-"}


def test_analyze_gaps_groups_consecutive_missing():
    service = KlineQualityService(FakeProvider())
    base = pd.Timestamp("2024-01-01 00:00:00")
    delta = pd.Timedelta(minutes=1)
    missing = [base + delta * 1, base + delta * 2, base + delta * 5]

    ranges = service._analyze_gaps(missing, delta)

    # 1-2 分钟连续归为一段，5 分钟单独一段
    assert len(ranges) == 2
    first = ranges[0]
    assert first["missing_count"] == 2
    assert first["start"] == str(base + delta * 1)


def test_analyze_gaps_empty():
    service = KlineQualityService(FakeProvider())
    assert service._analyze_gaps([], pd.Timedelta(minutes=1)) == []


def test_calculate_summary_weighted_scores():
    service = KlineQualityService(FakeProvider())
    details = {
        "integrity": {"status": "pass"},
        "continuity": {"status": "fail"},  # 0 分
        "validity": {"status": "pass"},
        "uniqueness": {"status": "pass"},
    }

    summary = service._calculate_summary(details)

    # 0.25 + 0.25 + 0.15 = 0.65 → 65 分
    assert summary["score"] == 65.0
    assert summary["grade"] == "C"
    assert summary["checks_passed"] == 3
    assert summary["checks_total"] == 4
