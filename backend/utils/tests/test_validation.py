"""
Tests for validation module
"""

from datetime import datetime

import pytest

from backend.utils.validation import (
    VALID_TIMEFRAMES,
    VALID_TRADING_MODES,
    get_default_values,
    parse_symbols,
    parse_time_range,
    parse_timeframes,
    validate_symbols,
    validate_time_range,
    validate_timeframes,
    validate_trading_mode,
)


class TestValidateTimeRange:
    """Tests for validate_time_range function"""

    def test_empty_time_range(self):
        """Test empty time range returns True"""
        assert validate_time_range(None) is True
        assert validate_time_range("") is True

    def test_valid_yyyymmdd_format(self):
        """Test valid YYYYMMDD-YYYYMMDD format"""
        assert validate_time_range("20240101-20241231") is True

    def test_valid_iso_date_format(self):
        """Test valid YYYY-MM-DD format"""
        assert validate_time_range("2024-01-01-2024-12-31") is True

    def test_valid_iso_datetime_format(self):
        """Test valid YYYY-MM-DD HH:MM:SS format"""
        assert validate_time_range("2024-01-01 00:00:00-2024-12-31 23:59:59") is True

    def test_invalid_format(self):
        """Test invalid formats"""
        assert validate_time_range("invalid") is False
        assert validate_time_range("20240101") is False
        assert validate_time_range("20240101-2024") is False
        assert validate_time_range("2024-13-01-2024-12-31") is False

    def test_start_after_end(self):
        """Test start date >= end date returns False"""
        assert validate_time_range("20241231-20240101") is False
        assert validate_time_range("2024-01-01-2024-01-01") is False


class TestParseTimeRange:
    """Tests for parse_time_range function"""

    def test_empty_time_range(self):
        """Test empty time range returns (None, None)"""
        assert parse_time_range(None) == (None, None)

    def test_valid_yyyymmdd_format(self):
        """Test valid YYYYMMDD-YYYYMMDD format"""
        start, end = parse_time_range("20240101-20241231")
        assert start == datetime(2024, 1, 1)
        assert end == datetime(2024, 12, 31)

    def test_valid_iso_date_format(self):
        """Test valid YYYY-MM-DD format"""
        start, end = parse_time_range("2024-01-01-2024-12-31")
        assert start == datetime(2024, 1, 1)
        assert end == datetime(2024, 12, 31)

    def test_valid_iso_datetime_format(self):
        """Test valid YYYY-MM-DD HH:MM:SS format"""
        start, end = parse_time_range("2024-01-01 00:00:00-2024-12-31 23:59:59")
        assert start == datetime(2024, 1, 1, 0, 0, 0)
        assert end == datetime(2024, 12, 31, 23, 59, 59)

    def test_invalid_format_raises_value_error(self):
        """Test invalid format raises ValueError"""
        with pytest.raises(ValueError):
            parse_time_range("invalid")
        with pytest.raises(ValueError):
            parse_time_range("20240101")

    def test_start_after_end_raises_value_error(self):
        """Test start date >= end date raises ValueError"""
        with pytest.raises(ValueError):
            parse_time_range("20241231-20240101")
        with pytest.raises(ValueError):
            parse_time_range("2024-01-01-2024-01-01")


class TestValidateSymbols:
    """Tests for validate_symbols function"""

    def test_empty_symbols(self):
        """Test empty symbols returns True"""
        assert validate_symbols(None) is True
        assert validate_symbols("") is True

    def test_valid_symbols(self):
        """Test valid symbols"""
        assert validate_symbols("BTCUSDT") is True
        assert validate_symbols("BTCUSDT,ETHUSDT") is True
        assert validate_symbols("BTCUSDT, ETHUSDT, SOLUSDT") is True

    def test_symbols_with_empty_string(self):
        """Test symbols with empty strings"""
        assert validate_symbols(",BTCUSDT,") is True
        assert validate_symbols("BTCUSDT,,ETHUSDT") is True


class TestParseSymbols:
    """Tests for parse_symbols function"""

    def test_empty_symbols(self):
        """Test empty symbols returns empty list"""
        assert parse_symbols(None) == []
        assert parse_symbols("") == []

    def test_single_symbol(self):
        """Test single symbol"""
        assert parse_symbols("BTCUSDT") == ["BTCUSDT"]

    def test_multiple_symbols(self):
        """Test multiple symbols"""
        assert parse_symbols("BTCUSDT,ETHUSDT") == ["BTCUSDT", "ETHUSDT"]
        assert parse_symbols("BTCUSDT, ETHUSDT, SOLUSDT") == [
            "BTCUSDT",
            "ETHUSDT",
            "SOLUSDT",
        ]

    def test_symbols_with_empty_string(self):
        """Test symbols with empty strings"""
        assert parse_symbols(",BTCUSDT,") == ["BTCUSDT"]
        assert parse_symbols("BTCUSDT,,ETHUSDT") == ["BTCUSDT", "ETHUSDT"]


class TestValidateTimeframes:
    """Tests for validate_timeframes function"""

    def test_empty_timeframes(self):
        """Test empty timeframes returns True"""
        assert validate_timeframes(None) is True
        assert validate_timeframes("") is True

    def test_valid_timeframes(self):
        """Test valid timeframes"""
        for tf in VALID_TIMEFRAMES:
            assert validate_timeframes(tf) is True
        assert validate_timeframes("1h,4h") is True
        assert validate_timeframes("1h, 4h, 1d") is True

    def test_invalid_timeframes(self):
        """Test invalid timeframes"""
        assert validate_timeframes("invalid") is False
        assert validate_timeframes("1h,invalid") is False
        assert validate_timeframes("1m") is False


class TestParseTimeframes:
    """Tests for parse_timeframes function"""

    def test_empty_timeframes(self):
        """Test empty timeframes returns empty list"""
        assert parse_timeframes(None) == []
        assert parse_timeframes("") == []

    def test_single_timeframe(self):
        """Test single timeframe"""
        assert parse_timeframes("1h") == ["1h"]

    def test_multiple_timeframes(self):
        """Test multiple timeframes"""
        assert parse_timeframes("1h,4h") == ["1h", "4h"]
        assert parse_timeframes("1h, 4h, 1d") == ["1h", "4h", "1d"]

    def test_timeframes_with_empty_string(self):
        """Test timeframes with empty strings"""
        assert parse_timeframes(",1h,") == ["1h"]
        assert parse_timeframes("1h,,4h") == ["1h", "4h"]


class TestValidateTradingMode:
    """Tests for validate_trading_mode function"""

    def test_empty_mode(self):
        """Test empty mode returns True"""
        assert validate_trading_mode(None) is True

    def test_valid_modes(self):
        """Test valid modes"""
        for mode in VALID_TRADING_MODES:
            assert validate_trading_mode(mode) is True

    def test_invalid_mode(self):
        """Test invalid mode"""
        assert validate_trading_mode("invalid") is False


class TestGetDefaultValues:
    """Tests for get_default_values function"""

    def test_get_default_values(self):
        """Test get_default_values returns expected dict"""
        defaults = get_default_values()
        assert isinstance(defaults, dict)
        assert defaults["trading_mode"] == "spot"
        assert defaults["timeframes"] == ["1h"]
        assert defaults["symbols"] == ["BTCUSDT"]
        assert defaults["init_cash"] == 100000.0
        assert defaults["fees"] == 0.001
        assert defaults["slippage"] == 0.0001
