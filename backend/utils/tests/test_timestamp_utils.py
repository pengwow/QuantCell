#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Timestamp utilities unit tests
"""

from datetime import datetime
import pytest

from utils.timestamp_utils import (
    detect_precision,
    to_nanoseconds,
    from_nanoseconds,
    normalize_to_nanoseconds,
    nanoseconds_to_datetime,
    datetime_to_nanoseconds,
    format_nanoseconds,
    parse_to_nanoseconds,
    milliseconds_to_nanoseconds,
    nanoseconds_to_milliseconds,
    batch_to_nanoseconds,
    batch_normalize_to_nanoseconds,
    is_valid_nanoseconds,
    validate_nanoseconds,
)


class TestDetectPrecision:
    """Tests for detect_precision function"""

    def test_seconds(self):
        """Test detecting second precision"""
        assert detect_precision(1767830400) == 's'

    def test_milliseconds(self):
        """Test detecting millisecond precision"""
        assert detect_precision(1767830400000) == 'ms'

    def test_microseconds(self):
        """Test detecting microsecond precision"""
        assert detect_precision(1767830400000000) == 'us'

    def test_nanoseconds(self):
        """Test detecting nanosecond precision"""
        assert detect_precision(1767830400000000000) == 'ns'

    def test_string_input(self):
        """Test string input"""
        assert detect_precision('1767830400') == 's'


class TestToNanoseconds:
    """Tests for to_nanoseconds function"""

    def test_auto_seconds(self):
        """Test auto-detect seconds"""
        assert to_nanoseconds(1767830400) == 1767830400000000000

    def test_auto_milliseconds(self):
        """Test auto-detect milliseconds"""
        assert to_nanoseconds(1767830400000) == 1767830400000000000

    def test_specified_precision(self):
        """Test using specified precision"""
        assert to_nanoseconds(1767830400, input_precision='s') == 1767830400000000000
        assert to_nanoseconds(1767830400000, input_precision='ms') == 1767830400000000000

    def test_float_input(self):
        """Test float input"""
        assert to_nanoseconds(1767830400.0) == 1767830400000000000

    def test_invalid_input(self):
        """Test invalid input raises error"""
        with pytest.raises(ValueError):
            to_nanoseconds('invalid')


class TestFromNanoseconds:
    """Tests for from_nanoseconds function"""

    def test_to_seconds(self):
        """Test converting to seconds"""
        assert from_nanoseconds(1767830400000000000, 's') == 1767830400

    def test_to_milliseconds(self):
        """Test converting to milliseconds"""
        assert from_nanoseconds(1767830400000000000, 'ms') == 1767830400000

    def test_to_microseconds(self):
        """Test converting to microseconds"""
        assert from_nanoseconds(1767830400000000000, 'us') == 1767830400000000

    def test_to_nanoseconds(self):
        """Test converting to nanoseconds (no-op)"""
        assert from_nanoseconds(1767830400000000000, 'ns') == 1767830400000000000

    def test_invalid_precision(self):
        """Test invalid precision raises error"""
        with pytest.raises(ValueError):
            from_nanoseconds(1767830400000000000, 'invalid')


class TestNormalizeToNanoseconds:
    """Tests for normalize_to_nanoseconds function"""

    def test_normalize(self):
        """Test normalization"""
        assert normalize_to_nanoseconds(1767830400) == '1767830400000000000'


class TestNanosecondsToDatetime:
    """Tests for nanoseconds_to_datetime function"""

    def test_conversion(self):
        """Test converting nanoseconds to datetime"""
        ts = 1767830400000000000  # 2026-01-08 00:00:00 UTC
        dt = nanoseconds_to_datetime(ts)
        # Note: This may be local time, so we'll check the date part
        assert dt.year == 2026
        assert dt.month == 1
        assert dt.day in (7, 8)  # Depending on timezone


class TestDatetimeToNanoseconds:
    """Tests for datetime_to_nanoseconds function"""

    def test_conversion(self):
        """Test converting datetime to nanoseconds"""
        dt = datetime(2026, 1, 8, 0, 0, 0)
        ts = datetime_to_nanoseconds(dt)
        assert str(ts).startswith('17678304')  # Should be similar to expected


class TestFormatNanoseconds:
    """Tests for format_nanoseconds function"""

    def test_format(self):
        """Test formatting"""
        ts = 1767830400000000000
        formatted = format_nanoseconds(ts)
        assert '2026' in formatted


class TestParseToNanoseconds:
    """Tests for parse_to_nanoseconds function"""

    def test_parse(self):
        """Test parsing"""
        ts = parse_to_nanoseconds("2026-01-08 00:00:00")
        assert str(ts).startswith('17678304')


class TestMillisecondsToNanoseconds:
    """Tests for milliseconds_to_nanoseconds function"""

    def test_conversion(self):
        """Test conversion"""
        assert milliseconds_to_nanoseconds(1767830400000) == 1767830400000000000


class TestNanosecondsToMilliseconds:
    """Tests for nanoseconds_to_milliseconds function"""

    def test_conversion(self):
        """Test conversion"""
        assert nanoseconds_to_milliseconds(1767830400000000000) == 1767830400000


class TestBatchToNanoseconds:
    """Tests for batch_to_nanoseconds function"""

    def test_batch(self):
        """Test batch conversion"""
        ts_list = [1767830400, 1767830401]
        result = batch_to_nanoseconds(ts_list)
        assert len(result) == 2
        assert result[0] == 1767830400000000000


class TestBatchNormalizeToNanoseconds:
    """Tests for batch_normalize_to_nanoseconds function"""

    def test_batch(self):
        """Test batch normalization"""
        ts_list = [1767830400, 1767830401]
        result = batch_normalize_to_nanoseconds(ts_list)
        assert len(result) == 2
        assert result[0] == '1767830400000000000'


class TestIsValidNanoseconds:
    """Tests for is_valid_nanoseconds function"""

    def test_valid(self):
        """Test valid nanosecond timestamp"""
        assert is_valid_nanoseconds(1767830400000000000) is True

    def test_invalid_too_small(self):
        """Test invalid small timestamp"""
        assert is_valid_nanoseconds(1767830400) is False

    def test_invalid_string(self):
        """Test invalid string"""
        assert is_valid_nanoseconds('invalid') is False


class TestValidateNanoseconds:
    """Tests for validate_nanoseconds function"""

    def test_valid(self):
        """Test valid case"""
        validate_nanoseconds(1767830400000000000)  # Should not raise

    def test_invalid(self):
        """Test invalid case raises error"""
        with pytest.raises(ValueError):
            validate_nanoseconds(1767830400)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
