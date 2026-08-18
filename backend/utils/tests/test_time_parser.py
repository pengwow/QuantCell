#!/usr/bin/env python3
"""
Time parser utilities unit tests
"""

from datetime import datetime

import pytest

from utils.time_parser import (
    align_to_interval,
    calculate_expected_klines,
    datetime_to_timestamp,
    format_date,
    format_datetime,
    get_date_range,
    get_interval_minutes,
    get_interval_ms,
    get_time_range_for_download,
    parse_time_range,
    str_to_timestamp,
    timestamp_to_datetime,
)


class TestParseTimeRange:
    """Tests for parse_time_range function"""

    def test_valid_range(self):
        """Test valid time range"""
        start, end = parse_time_range("20260101-20260131")
        assert start == datetime(2026, 1, 1)
        assert end == datetime(2026, 1, 31)

    def test_none_range(self):
        """Test None input"""
        start, end = parse_time_range(None)
        assert start is None
        assert end is None

    def test_invalid_format(self):
        """Test invalid format"""
        with pytest.raises(ValueError):
            parse_time_range("20260101to20260131")

    def test_start_after_end(self):
        """Test start date after end date"""
        with pytest.raises(ValueError):
            parse_time_range("20260131-20260101")


class TestDatetimeToTimestamp:
    """Tests for datetime_to_timestamp function"""

    def test_to_ms(self):
        """Test conversion to milliseconds"""
        dt = datetime(2026, 5, 10, 12, 0, 0)
        ts = datetime_to_timestamp(dt, unit="ms")
        assert isinstance(ts, int)

    def test_to_seconds(self):
        """Test conversion to seconds"""
        dt = datetime(2026, 5, 10, 12, 0, 0)
        ts = datetime_to_timestamp(dt, unit="s")
        assert isinstance(ts, int)


class TestTimestampToDatetime:
    """Tests for timestamp_to_datetime function"""

    def test_from_ms(self):
        """Test conversion from milliseconds"""
        dt1 = datetime(2026, 5, 10, 12, 0, 0)
        ts = datetime_to_timestamp(dt1, "ms")
        dt2 = timestamp_to_datetime(ts, "ms")
        assert abs((dt1 - dt2).total_seconds()) < 1

    def test_from_seconds(self):
        """Test conversion from seconds"""
        dt1 = datetime(2026, 5, 10, 12, 0, 0)
        ts = datetime_to_timestamp(dt1, "s")
        dt2 = timestamp_to_datetime(ts, "s")
        assert abs((dt1 - dt2).total_seconds()) < 1


class TestFormatDatetime:
    """Tests for format_datetime function"""

    def test_default_format(self):
        """Test default format"""
        dt = datetime(2026, 5, 10, 12, 34, 56)
        assert format_datetime(dt) == "2026-05-10 12:34:56"

    def test_custom_format(self):
        """Test custom format"""
        dt = datetime(2026, 5, 10)
        assert format_datetime(dt, "%Y/%m/%d") == "2026/05/10"


class TestFormatDate:
    """Tests for format_date function"""

    def test_default_format(self):
        """Test default format"""
        dt = datetime(2026, 5, 10)
        assert format_date(dt) == "20260510"


class TestGetIntervalMinutes:
    """Tests for get_interval_minutes function"""

    def test_common_intervals(self):
        """Test common intervals"""
        assert get_interval_minutes("1m") == 1
        assert get_interval_minutes("5m") == 5
        assert get_interval_minutes("15m") == 15
        assert get_interval_minutes("30m") == 30
        assert get_interval_minutes("1h") == 60
        assert get_interval_minutes("4h") == 240
        assert get_interval_minutes("1d") == 1440
        assert get_interval_minutes("1w") == 10080

    def test_unknown_interval(self):
        """Test unknown interval returns 1"""
        assert get_interval_minutes("unknown") == 1


class TestCalculateExpectedKlines:
    """Tests for calculate_expected_klines function"""

    def test_one_day_1h(self):
        """Test 1 day of 1h klines"""
        start = datetime(2026, 5, 10, 0, 0, 0)
        end = datetime(2026, 5, 11, 0, 0, 0)
        count = calculate_expected_klines(start, end, "1h")
        assert count == 25  # 24 hours + 1

    def test_one_hour_1m(self):
        """Test 1 hour of 1m klines"""
        start = datetime(2026, 5, 10, 0, 0, 0)
        end = datetime(2026, 5, 10, 1, 0, 0)
        count = calculate_expected_klines(start, end, "1m")
        assert count == 61


class TestAlignToInterval:
    """Tests for align_to_interval function"""

    def test_align_to_1h(self):
        """Test align to 1 hour interval"""
        dt = datetime(2026, 5, 10, 12, 34, 56)
        aligned = align_to_interval(dt, "1h")
        assert aligned == datetime(2026, 5, 10, 12, 0, 0)

    def test_align_to_15m(self):
        """Test align to 15 minute interval"""
        dt = datetime(2026, 5, 10, 12, 34, 56)
        aligned = align_to_interval(dt, "15m")
        assert aligned == datetime(2026, 5, 10, 12, 30, 0)

    def test_align_to_1d(self):
        """Test align to 1 day interval"""
        dt = datetime(2026, 5, 10, 12, 34, 56)
        aligned = align_to_interval(dt, "1d")
        assert aligned == datetime(2026, 5, 10, 0, 0, 0)


class TestGetTimeRangeForDownload:
    """Tests for get_time_range_for_download function"""

    def test_buffer_days(self):
        """Test adding buffer days"""
        start = datetime(2026, 5, 10)
        end = datetime(2026, 5, 20)
        buffered_start, buffered_end = get_time_range_for_download(start, end, buffer_days=2)
        assert buffered_start == datetime(2026, 5, 8)
        assert buffered_end == datetime(2026, 5, 22)


class TestGetDateRange:
    """Tests for get_date_range function"""

    def test_date_range(self):
        """Test getting date range list"""
        dates = get_date_range("2026-05-10", "2026-05-12")
        assert dates == ["2026-05-10", "2026-05-11", "2026-05-12"]


class TestGetIntervalMs:
    """Tests for get_interval_ms function"""

    def test_common_intervals(self):
        """Test common intervals in milliseconds"""
        assert get_interval_ms("1m") == 60 * 1000
        assert get_interval_ms("5m") == 5 * 60 * 1000
        assert get_interval_ms("1h") == 60 * 60 * 1000
        assert get_interval_ms("1d") == 24 * 60 * 60 * 1000


class TestStrToTimestamp:
    """Tests for str_to_timestamp function"""

    def test_date_only(self):
        """Test date only string"""
        ts = str_to_timestamp("2026-05-10", unit="ms")
        assert isinstance(ts, int)

    def test_datetime(self):
        """Test datetime string"""
        ts = str_to_timestamp("2026-05-10 12:34:56", unit="ms")
        assert isinstance(ts, int)

    def test_invalid_string(self):
        """Test invalid date string"""
        with pytest.raises(ValueError):
            str_to_timestamp("not a date")

    def test_none_or_empty(self):
        """Test None or empty input"""
        assert str_to_timestamp("") is None
        assert str_to_timestamp(None) is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
