# -*- coding: utf-8 -*-
"""
Timezone Utilities Unit Tests

Tests for the timezone module functions.
"""
import datetime
import os
import pytz
import pytest
from unittest.mock import patch, MagicMock

from backend.utils.timezone import (
    get_timezone,
    to_local_time,
    to_utc_time,
    format_datetime,
    parse_datetime,
    reload_timezone
)


class TestGetTimezone:
    """Tests for get_timezone function"""
    
    def test_get_from_env_var(self):
        """Test getting timezone from environment variable"""
        with patch.dict(os.environ, {"APP_TIMEZONE": "America/New_York"}):
            tz = get_timezone()
            assert tz.zone == "America/New_York"
    
    def test_get_from_config(self):
        """Test getting timezone from config"""
        # Mock config manager
        mock_config_manager = MagicMock()
        mock_config_manager.get.return_value = "Europe/London"
        with patch('backend.utils.timezone._get_config_manager', return_value=mock_config_manager):
            with patch.dict(os.environ, {}, clear=True):
                tz = get_timezone()
                assert tz.zone == "Europe/London"
                mock_config_manager.get.assert_called_once_with("app.timezone", "Asia/Shanghai")
    
    def test_default_timezone(self):
        """Test default timezone when config not set"""
        mock_config_manager = MagicMock()
        mock_config_manager.get.return_value = None
        with patch('backend.utils.timezone._get_config_manager', return_value=mock_config_manager):
            with patch.dict(os.environ, {}, clear=True):
                tz = get_timezone()
                assert tz.zone == "Asia/Shanghai"
    
    def test_invalid_timezone_fallback(self):
        """Test fallback to default when invalid timezone is provided"""
        mock_config_manager = MagicMock()
        mock_config_manager.get.return_value = "Invalid/Timezone"
        with patch('backend.utils.timezone._get_config_manager', return_value=mock_config_manager):
            with patch('backend.utils.timezone.logger') as mock_logger:
                tz = get_timezone()
                assert tz.zone == "Asia/Shanghai"
                mock_logger.error.assert_called_once()
    
    def test_reload_timezone(self):
        """Test reloading timezone configuration"""
        # First load
        with patch.dict(os.environ, {"APP_TIMEZONE": "America/New_York"}):
            tz1 = get_timezone()
            assert tz1.zone == "America/New_York"
        
        # Reload
        reload_timezone()
        
        # Second load with different env var
        with patch.dict(os.environ, {"APP_TIMEZONE": "Europe/London"}):
            tz2 = get_timezone()
            assert tz2.zone == "Europe/London"


class TestToLocalTime:
    """Tests for to_local_time function"""
    
    def test_none_input(self):
        """Test converting None"""
        assert to_local_time(None) is None
    
    def test_naive_datetime(self):
        """Test converting naive datetime (no timezone info)"""
        utc_dt = datetime.datetime(2023, 1, 1, 12, 0, 0)
        with patch('backend.utils.timezone.get_timezone', return_value=pytz.timezone("Asia/Shanghai")):
            local_dt = to_local_time(utc_dt)
            assert local_dt.tzinfo is not None
            assert local_dt.hour == 20  # UTC+8
    
    def test_aware_datetime(self):
        """Test converting aware datetime"""
        utc_tz = pytz.utc
        utc_dt = utc_tz.localize(datetime.datetime(2023, 1, 1, 12, 0, 0))
        with patch('backend.utils.timezone.get_timezone', return_value=pytz.timezone("Asia/Shanghai")):
            local_dt = to_local_time(utc_dt)
            assert local_dt.hour == 20


class TestToUtcTime:
    """Tests for to_utc_time function"""
    
    def test_none_input(self):
        """Test converting None"""
        assert to_utc_time(None) is None
    
    def test_naive_datetime(self):
        """Test converting naive datetime (no timezone info)"""
        local_tz = pytz.timezone("Asia/Shanghai")
        local_dt = local_tz.localize(datetime.datetime(2023, 1, 1, 20, 0, 0))
        with patch('backend.utils.timezone.get_timezone', return_value=local_tz):
            utc_dt = to_utc_time(local_dt.replace(tzinfo=None))
            assert utc_dt.tzinfo == pytz.utc
            assert utc_dt.hour == 12  # UTC+8
    
    def test_aware_datetime(self):
        """Test converting aware datetime"""
        local_tz = pytz.timezone("Asia/Shanghai")
        local_dt = local_tz.localize(datetime.datetime(2023, 1, 1, 20, 0, 0))
        utc_dt = to_utc_time(local_dt)
        assert utc_dt.tzinfo == pytz.utc
        assert utc_dt.hour == 12


class TestFormatDatetime:
    """Tests for format_datetime function"""
    
    def test_none_input(self):
        """Test formatting None"""
        assert format_datetime(None) is None
    
    def test_formatting(self):
        """Test formatting datetime"""
        utc_dt = datetime.datetime(2023, 1, 1, 12, 0, 0, tzinfo=pytz.utc)
        with patch('backend.utils.timezone.get_timezone', return_value=pytz.timezone("Asia/Shanghai")):
            formatted = format_datetime(utc_dt)
            assert formatted == "2023-01-01 20:00:00"
    
    def test_custom_format(self):
        """Test with custom format string"""
        utc_dt = datetime.datetime(2023, 1, 1, 12, 0, 0, tzinfo=pytz.utc)
        with patch('backend.utils.timezone.get_timezone', return_value=pytz.timezone("Asia/Shanghai")):
            formatted = format_datetime(utc_dt, "%Y/%m/%d")
            assert formatted == "2023/01/01"


class TestParseDatetime:
    """Tests for parse_datetime function"""
    
    def test_empty_string(self):
        """Test parsing empty string"""
        assert parse_datetime("") is None
    
    def test_parsing(self):
        """Test parsing datetime string"""
        with patch('backend.utils.timezone.get_timezone', return_value=pytz.timezone("Asia/Shanghai")):
            dt = parse_datetime("2023-01-01 20:00:00")
            assert dt is not None
            assert dt.year == 2023
            assert dt.month == 1
            assert dt.day == 1
            assert dt.hour == 20
    
    def test_custom_format(self):
        """Test with custom format string"""
        with patch('backend.utils.timezone.get_timezone', return_value=pytz.timezone("Asia/Shanghai")):
            dt = parse_datetime("2023/01/01", "%Y/%m/%d")
            assert dt is not None
            assert dt.year == 2023
            assert dt.month == 1
            assert dt.day == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

