"""collector.services.kline_health_service 单元测试。

覆盖：
- get_kline_data: 市场/加密货币类型分支、时间范围过滤、排序
- check_integrity / check_continuity / check_coverage / check_validity
- check_consistency / check_uniqueness / check_logic / check_all
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from collector.services.kline_health_service import KlineHealthChecker
from utils.timestamp_utils import datetime_to_nanoseconds


def make_df(timestamps_ns: list[int], **overrides) -> pd.DataFrame:
    """构造可供检查的 K 线 DataFrame，带 id 列。"""
    n = len(timestamps_ns)
    data = {
        "id": list(range(1, n + 1)),
        "timestamp": timestamps_ns,
        "open": [100.0] * n,
        "high": [101.0] * n,
        "low": [99.0] * n,
        "close": [100.0] * n,
        "volume": [1000.0] * n,
    }
    data.update(overrides)
    return pd.DataFrame(data)


def ns_ts(start: datetime, minutes: list[int]) -> list[int]:
    return [datetime_to_nanoseconds(start + timedelta(minutes=m)) for m in minutes]


@pytest.fixture
def checker():
    """绕过 __init__（会触发真实的 init_database_config + SessionLocal），
    仅注入 mock 的 db 会话，保证测试不触碰真实数据库。"""
    instance = KlineHealthChecker.__new__(KlineHealthChecker)
    instance.db = MagicMock()
    return instance


def _kline_row(index: int, ts_ns: int, **kwargs) -> MagicMock:
    row = MagicMock()
    row.id = index
    row.timestamp = str(ts_ns)
    row.open = kwargs.get("open", "100")
    row.high = kwargs.get("high", "101")
    row.low = kwargs.get("low", "99")
    row.close = kwargs.get("close", "100")
    row.volume = kwargs.get("volume", "1000")
    return row


# =================== get_kline_data ===================


class TestGetKlineData:
    def test_unsupported_market_type_returns_empty(self, checker):
        df = checker.get_kline_data("BTCUSDT", "1m", market_type="forex")
        assert df.empty

    def test_unsupported_crypto_type_returns_empty(self, checker):
        df = checker.get_kline_data("BTCUSDT", "1m", crypto_type="option")
        assert df.empty

    def test_spot_query_and_shape(self, checker):
        base = datetime(2026, 1, 1, tzinfo=UTC)
        rows = [
            _kline_row(1, datetime_to_nanoseconds(base + timedelta(minutes=1))),
            _kline_row(2, datetime_to_nanoseconds(base + timedelta(minutes=2))),
        ]
        checker.db.query.return_value.filter.return_value.all.return_value = rows

        df = checker.get_kline_data("BTCUSDT", "1m")

        checker.db.query.assert_called_once()
        assert list(df.columns) == ["id", "timestamp", "open", "high", "low", "close", "volume"]
        assert len(df) == 2
        # 按时间戳升序
        assert df.iloc[0]["id"] == 1

    def test_future_and_stock_model_selection(self, checker):
        from collector.db.models import CryptoFutureKline, StockKline

        checker.db.query.return_value.filter.return_value.all.return_value = [_kline_row(1, "1")]
        checker.get_kline_data("BTCUSDT", "1m", market_type="crypto", crypto_type="future")
        checker.db.query.assert_called_with(CryptoFutureKline)
        checker.db.query.return_value.filter.assert_called_once()

        checker.db.query.reset_mock()
        checker.get_kline_data("600000", "1d", market_type="stock")
        checker.db.query.assert_called_with(StockKline)

    def test_time_range_filter(self, checker):
        # get_kline_data 内部按 UTC 视口处理 start/end，传入 naive datetime 即可
        base = datetime(2026, 1, 1)
        ts_all = [datetime_to_nanoseconds(base + timedelta(minutes=i)) for i in range(3)]
        rows = [_kline_row(i, ts) for i, ts in enumerate(ts_all, start=1)]
        checker.db.query.return_value.filter.return_value.all.return_value = rows

        start = base + timedelta(minutes=1)
        df = checker.get_kline_data("BTCUSDT", "1m", start=start)
        assert len(df) == 2
        assert df["id"].tolist() == [2, 3]

        end = base + timedelta(minutes=1)
        df = checker.get_kline_data("BTCUSDT", "1m", end=end)
        assert len(df) == 2
        assert df["id"].tolist() == [1, 2]

        df = checker.get_kline_data("BTCUSDT", "1m", start=start, end=end)
        assert len(df) == 1
        assert df["id"].tolist() == [2]

    def test_empty_query_returns_empty_df(self, checker):
        checker.db.query.return_value.filter.return_value.all.return_value = []
        df = checker.get_kline_data("BTCUSDT", "1m")
        assert df.empty


# =================== check_integrity ===================


class TestCheckIntegrity:
    def test_pass_with_complete_data(self):
        df = make_df([1, 2, 3])
        result = KlineHealthChecker.__new__(KlineHealthChecker).check_integrity(df)
        assert result["status"] == "pass"
        assert result["total_records"] == 3
        assert result["missing_columns"] == []
        assert result["missing_values"] == []

    def test_fail_missing_columns(self, checker):
        df = make_df([1]).drop(columns=["high"])
        result = checker.check_integrity(df)
        assert result["status"] == "fail"
        assert "high" in result["missing_columns"]

    def test_fail_missing_values(self, checker):
        df = make_df([1, 2], close=[None, 100.0])
        result = checker.check_integrity(df)
        assert result["status"] == "fail"
        assert result["missing_values"]["close"] == 1

    def test_empty_df_missing_all_columns(self, checker):
        # 空 DataFrame 无必需列，完整性判定为 fail
        result = checker.check_integrity(pd.DataFrame())
        assert result["status"] == "fail"
        assert len(result["missing_columns"]) == 5
        assert result["total_records"] == 0


# =================== check_continuity ===================


class TestCheckContinuity:
    def test_empty_df_returns_default(self, checker):
        result = checker.check_continuity(pd.DataFrame(), "1m")
        assert result["status"] == "pass"

    def test_unsupported_interval_returns_default(self, checker):
        df = make_df([1, 2])
        result = checker.check_continuity(df, "2m")
        assert result["status"] == "pass"
        assert result["actual_records"] == 2

    def test_continuous_data_passes(self, checker):
        base = datetime(2026, 1, 1, tzinfo=UTC)
        df = make_df(ns_ts(base, [0, 1, 2]))
        result = checker.check_continuity(df, "1m")
        assert result["status"] == "pass"
        assert result["missing_records"] == 0
        assert result["coverage_ratio"] == 1.0
        assert result["expected_records"] == 3

    def test_gap_detected(self, checker):
        base = datetime(2026, 1, 1, tzinfo=UTC)
        df = make_df(ns_ts(base, [0, 1, 3]))
        result = checker.check_continuity(df, "1m")
        assert result["status"] == "fail"
        assert result["missing_records"] == 1
        assert "2026-01-01 00:02:00" in result["missing_periods"]
        assert result["coverage_ratio"] == pytest.approx(3 / 4)
        # 缺失时间段被整合为一个区间
        assert len(result["missing_time_ranges"]) == 1
        assert result["missing_time_ranges"][0]["count"] == 1

    def test_disjoint_gaps_split_into_ranges(self, checker):
        # 实际 [0, 2, 5] 分钟，缺失 [1] 与 [3, 4] 两段不相连的区间
        base = datetime(2026, 1, 1, tzinfo=UTC)
        df = make_df(ns_ts(base, [0, 2, 5]))
        result = checker.check_continuity(df, "1m")
        assert result["status"] == "fail"
        assert result["missing_records"] == 3
        assert len(result["missing_time_ranges"]) == 2
        assert result["missing_time_ranges"][0]["count"] == 1
        assert result["missing_time_ranges"][1]["count"] == 2


# =================== check_coverage ===================


class TestCheckCoverage:
    def test_empty_df_fails(self, checker):
        result = checker.check_coverage(pd.DataFrame(), "1m", "BTCUSDT")
        assert result["status"] == "fail"

    def test_full_coverage_passes(self, checker):
        # 数据从 2023-01-01 覆盖到今天，历史与未来均无缺失
        start = datetime(2023, 1, 1, tzinfo=UTC)
        end = datetime.now(UTC)
        df = make_df(
            [datetime_to_nanoseconds(start), datetime_to_nanoseconds(end)],
            close=[100.0, 100.1],
        )
        result = checker.check_coverage(df, "1d", "BTCUSDT")
        assert result["status"] == "pass"
        assert result["missing_historical_data"] is False
        assert result["missing_future_data"] is False

    def test_missing_historical_data_fails(self, checker):
        # 数据从 2024 年开始，早于 2023-01-01 的缺失段被判为缺失历史数据
        base = datetime(2024, 1, 1, tzinfo=UTC)
        df = make_df(ns_ts(base, [0, 1]))
        result = checker.check_coverage(df, "5m", "BTCUSDT")
        assert result["status"] == "fail"
        assert result["missing_historical_data"] is True
        assert result["historical_gap_days"] > 0

    def test_missing_future_data_fails(self, checker):
        # 最新数据停在很久以前，超过 1 天容差判为缺失未来数据
        df = make_df(ns_ts(datetime(2023, 1, 1, tzinfo=UTC), [0, 1]))
        result = checker.check_coverage(df, "1d", "BTCUSDT")
        assert result["status"] == "fail"
        assert result["missing_future_data"] is True
        assert result["future_gap_days"] > 0


# =================== check_validity ===================


class TestCheckValidity:
    def test_empty_df_returns_pass(self, checker):
        result = checker.check_validity(pd.DataFrame())
        assert result["status"] == "pass"

    def test_pass_on_valid_data(self, checker):
        base = datetime(2026, 1, 1, tzinfo=UTC)
        df = make_df(ns_ts(base, [0, 1]))
        result = checker.check_validity(df)
        assert result["status"] == "pass"
        assert result["total_invalid_records"] == 0

    def test_negative_price(self, checker):
        df = make_df([1], open=[-1.0])
        result = checker.check_validity(df)
        assert result["status"] == "fail"
        assert len(result["negative_prices"]) == 1

    def test_negative_volume(self, checker):
        df = make_df([1], volume=[-10.0])
        result = checker.check_validity(df)
        assert result["status"] == "fail"
        assert len(result["negative_volumes"]) == 1

    def test_invalid_high_low(self, checker):
        df = make_df([1], high=[99.0], low=[101.0])
        result = checker.check_validity(df)
        assert result["status"] == "fail"
        assert len(result["invalid_high_low"]) == 1

    def test_invalid_price_logic(self, checker):
        # high 低于 max(open, close)
        df = make_df([1], open=[100.0], high=[95.0], close=[120.0])
        result = checker.check_validity(df)
        assert result["status"] == "fail"
        assert len(result["invalid_price_logic"]) == 1

    def test_abnormal_price_change(self, checker):
        base = datetime(2026, 1, 1, tzinfo=UTC)
        df = make_df(ns_ts(base, [0, 1]), close=[100.0, 150.0])
        result = checker.check_validity(df)
        assert result["status"] == "fail"
        assert len(result["abnormal_price_changes"]) == 1

    def test_abnormal_volume(self, checker):
        base = datetime(2026, 1, 1, tzinfo=UTC)
        timestamps = ns_ts(base, list(range(31)))
        df = make_df(timestamps, volume=[100.0] * 30 + [5000.0])
        result = checker.check_validity(df)
        assert result["status"] == "fail"
        assert len(result["abnormal_volumes"]) == 1

    def test_price_gap(self, checker):
        base = datetime(2026, 1, 1, tzinfo=UTC)
        df = make_df(ns_ts(base, [0, 1]), open=[100.0, 110.0], close=[100.0, 101.0])
        result = checker.check_validity(df)
        assert result["status"] == "fail"
        assert len(result["price_gaps"]) == 1


# =================== check_consistency ===================


class TestCheckConsistency:
    def test_empty_df_returns_default(self, checker):
        result = checker.check_consistency(pd.DataFrame())
        assert result["status"] == "pass"

    def test_duplicate_codes(self, checker):
        df = make_df([1, 2, 3], code=["600000", "600000", "600001"])
        result = checker.check_consistency(df)
        assert result["status"] == "fail"
        assert len(result["duplicate_codes"]) == 1

    def test_adj_factor_mixed_increasing_decreasing(self, checker):
        df = make_df([1, 2, 3, 4], adj_factor=[1.0, 2.0, 1.5, 2.5])
        result = checker.check_consistency(df)
        assert result["status"] == "fail"
        assert len(result["inconsistent_adj_factors"]) == 1

    def test_adj_factor_monotonic_passes(self, checker):
        df = make_df([1, 2, 3], adj_factor=[1.0, 1.1, 1.2])
        result = checker.check_consistency(df)
        assert result["status"] == "pass"

    def test_adj_factor_mostly_increasing_with_dips(self, checker):
        # 递增为主但夹带个别回撤（4 增 1 减），命中“复权因子非递增”告警
        df = make_df([1, 2, 3, 4, 5, 6], adj_factor=[1.0, 1.1, 1.2, 1.3, 1.1, 1.4])
        result = checker.check_consistency(df)
        assert result["status"] == "fail"
        assert any("非递增" in msg for msg in result["inconsistent_adj_factors"])

    def test_adj_factor_mostly_decreasing_with_bumps(self, checker):
        # 递减因子为主但夹带个别上调（3 减 1 增），同样判定复权因子不一致
        df = make_df([1, 2, 3, 4, 5], adj_factor=[1.4, 1.3, 1.2, 1.1, 1.3])
        result = checker.check_consistency(df)
        assert result["status"] == "fail"
        assert any("非递增" in msg for msg in result["inconsistent_adj_factors"])


# =================== check_uniqueness ===================


class TestCheckUniqueness:
    def test_empty_df_returns_default(self, checker):
        result = checker.check_uniqueness(pd.DataFrame())
        assert result["status"] == "pass"

    def test_duplicate_timestamps(self, checker):
        ts = [1, 1, 2]
        df = make_df(ts)
        result = checker.check_uniqueness(df)
        assert result["status"] == "fail"
        assert result["duplicate_records"] == 2
        assert len(result["duplicate_periods"]) == 1
        # 重复组按 timestamp 分组，第 0、1 行为一组
        assert len(result["duplicate_details"]) == 1

    def test_duplicate_details_structure(self, checker):
        # 验证每个重复组内记录详情（id/价格/row_number）可序列化
        df = make_df([1, 1, 2], close=[100.0, 101.0, 102.0])
        result = checker.check_uniqueness(df)
        detail = result["duplicate_details"][0]
        assert detail["group_type"] == "timestamp_duplicate"
        assert detail["key"] == "1"
        assert detail["count"] == 2
        assert detail["records"][0]["row_number"] == 1
        assert detail["records"][1]["row_number"] == 2
        assert detail["records"][1]["close"] == 101.0

    def test_duplicate_code_timestamp(self, checker):
        df = make_df([1, 1, 2], code=["600000", "600000", "600001"])
        result = checker.check_uniqueness(df)
        assert result["status"] == "fail"
        # timestamp 重复 + code+timestamp 重复都会被记入
        assert result["duplicate_records"] >= 2
        assert len(result["duplicate_code_timestamp"]) == 1

    def test_without_timestamp_column_skips(self, checker):
        df = pd.DataFrame({"open": [1.0]})
        result = checker.check_uniqueness(df)
        assert result["status"] == "pass"


# =================== check_logic ===================


class TestCheckLogic:
    def test_pass_on_normal_data(self, checker):
        base = datetime(2026, 1, 1, tzinfo=UTC)
        df = make_df(ns_ts(base, [0, 1, 2]), volume=[100.0, 200.0, 300.0])
        result = checker.check_logic(df, "1m")
        assert result["status"] == "pass"

    def test_suspension_with_missing_price(self, checker):
        # 成交量为 0 且价格不变视为停牌，此时价格字段缺失应被标记
        base = datetime(2026, 1, 1, tzinfo=UTC)
        df = make_df(
            ns_ts(base, [0, 1]),
            open=[100.0, None],
            high=[101.0, None],
            low=[99.0, None],
            close=[100.0, 100.0],
            volume=[100.0, 0.0],
        )
        result = checker.check_logic(df, "1d")
        assert result["status"] == "fail"
        assert len(result["suspension_issues"]) == 1

    def test_price_limit_exceeded(self, checker):
        base = datetime(2026, 1, 1, tzinfo=UTC)
        df = make_df(ns_ts(base, [0, 1]), close=[100.0, 120.0])
        result = checker.check_logic(df, "1d")
        assert result["status"] == "fail"
        assert len(result["price_limit_issues"]) == 1


# =================== check_all ===================


class TestCheckAll:
    def _checker_with_data(self, df: pd.DataFrame) -> KlineHealthChecker:
        checker = KlineHealthChecker.__new__(KlineHealthChecker)
        checker.db = MagicMock()
        checker.get_kline_data = MagicMock(return_value=df)
        return checker

    def test_overall_pass(self):
        base = datetime(2026, 1, 1, tzinfo=UTC)
        df = make_df(ns_ts(base, [0, 1, 2]))
        checker = self._checker_with_data(df)
        # 注入通过的子检查，聚焦汇总逻辑
        with (
            patch.object(checker, "check_integrity", return_value={"status": "pass"}),
            patch.object(checker, "check_continuity", return_value={"status": "pass"}),
            patch.object(checker, "check_validity", return_value={"status": "pass"}),
            patch.object(checker, "check_consistency", return_value={"status": "pass"}),
            patch.object(checker, "check_logic", return_value={"status": "pass"}),
            patch.object(checker, "check_uniqueness", return_value={"status": "pass"}),
            patch.object(checker, "check_coverage", return_value={"status": "pass"}),
        ):
            result = checker.check_all("BTCUSDT", "1m")
        assert result["overall_status"] == "pass"
        assert result["total_records"] == 3
        assert result["start_time"] is None

    def test_overall_fail_when_any_check_fails(self):
        base = datetime(2026, 1, 1, tzinfo=UTC)
        df = make_df(ns_ts(base, [0, 1]))
        checker = self._checker_with_data(df)
        with (
            patch.object(checker, "check_integrity", return_value={"status": "pass"}),
            patch.object(checker, "check_continuity", return_value={"status": "pass"}),
            patch.object(checker, "check_validity", return_value={"status": "fail"}),
            patch.object(checker, "check_consistency", return_value={"status": "pass"}),
            patch.object(checker, "check_logic", return_value={"status": "pass"}),
            patch.object(checker, "check_uniqueness", return_value={"status": "pass"}),
            patch.object(checker, "check_coverage", return_value={"status": "pass"}),
        ):
            result = checker.check_all("BTCUSDT", "1m")
        assert result["overall_status"] == "fail"

    def test_start_end_times_serialized(self):
        checker = KlineHealthChecker.__new__(KlineHealthChecker)
        checker.db = MagicMock()
        df = make_df([datetime_to_nanoseconds(datetime(2026, 1, 1, tzinfo=UTC))])
        with (
            patch.object(checker, "get_kline_data", return_value=df),
            patch.object(checker, "check_integrity", return_value={"status": "pass"}),
            patch.object(checker, "check_continuity", return_value={"status": "pass"}),
            patch.object(checker, "check_validity", return_value={"status": "pass"}),
            patch.object(checker, "check_consistency", return_value={"status": "pass"}),
            patch.object(checker, "check_logic", return_value={"status": "pass"}),
            patch.object(checker, "check_uniqueness", return_value={"status": "pass"}),
            patch.object(checker, "check_coverage", return_value={"status": "pass"}),
        ):
            result = checker.check_all(
                "BTCUSDT",
                "1m",
                start=datetime(2026, 1, 1, tzinfo=UTC),
                end=datetime(2026, 1, 2, tzinfo=UTC),
            )
        assert result["start_time"] == "2026-01-01T00:00:00+00:00"
        assert result["end_time"] == "2026-01-02T00:00:00+00:00"


# =================== 生命周期 ===================


class TestLifecycle:
    def test_init_initializes_database_and_results(self):
        # init_database_config 是 __init__ 函数内 import 的，需 patch 源模块；
        # SessionLocal 是模块级 import，直接 patch 模块属性即可
        with (
            patch("collector.db.database.init_database_config") as m_init,
            patch("collector.services.kline_health_service.SessionLocal", return_value=MagicMock()) as m_session,
        ):
            checker = KlineHealthChecker()
        m_init.assert_called_once()
        m_session.assert_called_once()
        assert checker.results["summary"] == {}
        assert checker.results["details"] == {
            "integrity": {},
            "continuity": {},
            "validity": {},
            "uniqueness": {},
        }
        checker.__del__()

    def test_del_closes_db(self):
        checker = KlineHealthChecker.__new__(KlineHealthChecker)
        checker.db = MagicMock()
        checker.__del__()
        checker.db.close.assert_called_once()

    def test_del_without_db_is_noop(self):
        # 通过 __new__ 构造的实例可能尚未初始化 db，__del__ 需静默跳过
        checker = KlineHealthChecker.__new__(KlineHealthChecker)
        checker.__del__()  # 不应抛 AttributeError
