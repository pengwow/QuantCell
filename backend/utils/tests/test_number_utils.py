# -*- coding: utf-8 -*-
"""
Number Utilities Unit Tests

Tests for the number_utils module functions.

作者: QuantCell Team
版本: 1.0.0
日期: 2026-02-27
"""

from decimal import Decimal
import pytest
from unittest.mock import patch

from backend.utils.number_utils import safe_float, safe_int, safe_decimal, parse_percentage


class TestSafeFloat:
    """Tests for safe_float function"""

    def test_string_with_commas(self):
        """Test converting string with commas"""
        assert safe_float("1,000.50") == 1000.5
        assert safe_float("1,000,000.99") == 1000000.99
        assert safe_float("  1,000  ") == 1000.0

    def test_string_without_commas(self):
        """Test converting string without commas"""
        assert safe_float("1000.50") == 1000.5
        assert safe_float("1000") == 1000.0
        assert safe_float("  1000.5  ") == 1000.5

    def test_integer(self):
        """Test converting integer"""
        assert safe_float(1000) == 1000.0
        assert safe_float(0) == 0.0
        assert safe_float(-100) == -100.0

    def test_float(self):
        """Test converting float"""
        assert safe_float(1000.5) == 1000.5
        assert safe_float(0.0) == 0.0
        assert safe_float(-100.5) == -100.5

    def test_decimal(self):
        """Test converting Decimal"""
        assert safe_float(Decimal("1000.50")) == 1000.5
        assert safe_float(Decimal("0")) == 0.0
        assert safe_float(Decimal("-100.5")) == -100.5

    def test_none(self):
        """Test converting None"""
        assert safe_float(None) == 0.0
        assert safe_float(None, default=-1.0) == -1.0

    def test_empty_string(self):
        """Test converting empty string"""
        assert safe_float("") == 0.0
        assert safe_float("   ") == 0.0

    def test_invalid_string(self):
        """Test converting invalid string"""
        with patch('backend.utils.number_utils.logger') as mock_logger:
            result = safe_float("abc", field_name="price")
            assert result == 0.0
            mock_logger.warning.assert_called_once_with("无法转换 price 数值: abc")

    def test_invalid_string_no_field_name(self):
        """Test converting invalid string without field name"""
        with patch('backend.utils.number_utils.logger') as mock_logger:
            result = safe_float("abc")
            assert result == 0.0
            mock_logger.warning.assert_not_called()

    def test_custom_default(self):
        """Test custom default value"""
        assert safe_float("invalid", default=-999.0) == -999.0
        assert safe_float(None, default=-1.0) == -1.0


class TestSafeInt:
    """Tests for safe_int function"""

    def test_string_with_commas(self):
        """Test converting string with commas"""
        assert safe_int("1,000") == 1000
        assert safe_int("1,000,000") == 1000000

    def test_string_float(self):
        """Test converting string float (truncates decimal)"""
        assert safe_int("1000.9") == 1000
        assert safe_int("1000.1") == 1000

    def test_integer(self):
        """Test converting integer"""
        assert safe_int(1000) == 1000
        assert safe_int(0) == 0
        assert safe_int(-100) == -100

    def test_float(self):
        """Test converting float (truncates decimal)"""
        assert safe_int(1000.9) == 1000
        assert safe_int(1000.1) == 1000

    def test_decimal(self):
        """Test converting Decimal"""
        assert safe_int(Decimal("1000")) == 1000
        assert safe_int(Decimal("1000.9")) == 1000

    def test_none(self):
        """Test converting None"""
        assert safe_int(None) == 0
        assert safe_int(None, default=-1) == -1

    def test_invalid_string(self):
        """Test converting invalid string"""
        with patch('backend.utils.number_utils.logger') as mock_logger:
            result = safe_int("abc", field_name="count")
            assert result == 0
            mock_logger.warning.assert_called_once_with("无法转换 count 数值: abc")


class TestSafeDecimal:
    """Tests for safe_decimal function"""

    def test_string_with_commas(self):
        """Test converting string with commas"""
        assert safe_decimal("1,000.50") == Decimal("1000.50")
        assert safe_decimal("1,000,000.99") == Decimal("1000000.99")

    def test_integer(self):
        """Test converting integer"""
        assert safe_decimal(1000) == Decimal("1000")
        assert safe_decimal(0) == Decimal("0")

    def test_float(self):
        """Test converting float"""
        assert safe_decimal(1000.5) == Decimal("1000.5")
        assert safe_decimal(0.0) == Decimal("0.0")

    def test_decimal(self):
        """Test converting Decimal (returns same)"""
        original = Decimal("1000.50")
        result = safe_decimal(original)
        assert result == original
        assert result is original  # Should return the same object

    def test_none(self):
        """Test converting None"""
        assert safe_decimal(None) == Decimal(0)
        assert safe_decimal(None, default=Decimal("-1")) == Decimal("-1")

    def test_invalid_string(self):
        """Test converting invalid string"""
        with patch('backend.utils.number_utils.logger') as mock_logger:
            result = safe_decimal("abc", field_name="amount")
            assert result == Decimal(0)
            mock_logger.warning.assert_called_once_with("无法转换 amount 数值: abc")


class TestParsePercentage:
    """Tests for parse_percentage function"""

    def test_string_with_percent_sign(self):
        """Test parsing string with % sign"""
        assert parse_percentage("50%") == 0.5
        assert parse_percentage("100%") == 1.0
        assert parse_percentage("0%") == 0.0

    def test_integer_percentage(self):
        """Test parsing integer (treated as percentage)"""
        assert parse_percentage(50) == 0.5
        assert parse_percentage(100) == 1.0
        assert parse_percentage(0) == 0.0

    def test_decimal_percentage(self):
        """Test parsing decimal (treated as decimal)"""
        assert parse_percentage(0.5) == 0.5
        assert parse_percentage(1.0) == 1.0
        assert parse_percentage(0.0) == 0.0

    def test_string_decimal(self):
        """Test parsing string decimal"""
        assert parse_percentage("0.5") == 0.5
        assert parse_percentage("1.0") == 1.0

    def test_greater_than_one(self):
        """Test values greater than 1 are treated as percentages"""
        assert parse_percentage(50) == 0.5  # 50 means 50%
        assert parse_percentage(75) == 0.75  # 75 means 75%

    def test_less_than_or_equal_one(self):
        """Test values <= 1 are treated as decimals"""
        assert parse_percentage(0.5) == 0.5  # Already decimal
        assert parse_percentage(1.0) == 1.0  # Already decimal

    def test_invalid(self):
        """Test invalid percentage"""
        assert parse_percentage("invalid") == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
