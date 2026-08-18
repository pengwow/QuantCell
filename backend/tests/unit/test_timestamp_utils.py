"""
时间戳工具模块单元测试

测试 timestamp_utils 模块的时间戳处理功能。

作者: QuantCell Team
版本: 1.0.0
日期: 2026-05-09
"""

from datetime import datetime

import pytest

from utils.timestamp_utils import (
    batch_normalize_to_nanoseconds,
    batch_to_nanoseconds,
    datetime_to_nanoseconds,
    detect_precision,
    format_nanoseconds,
    from_nanoseconds,
    is_valid_nanoseconds,
    milliseconds_to_nanoseconds,
    nanoseconds_to_datetime,
    nanoseconds_to_milliseconds,
    normalize_to_nanoseconds,
    parse_to_nanoseconds,
    to_nanoseconds,
    validate_nanoseconds,
)


class TestDetectPrecision:
    """测试 detect_precision 函数"""

    def test_seconds_precision(self):
        """测试秒级时间戳 (10位)"""
        assert detect_precision(1767830400) == "s"
        assert detect_precision(0) == "s"
        assert detect_precision(9999999999) == "s"

    def test_milliseconds_precision(self):
        """测试毫秒级时间戳 (13位)"""
        assert detect_precision(1767830400000) == "ms"
        assert detect_precision(10000000000000) == "ms"

    def test_microseconds_precision(self):
        """测试微秒级时间戳 (16位)"""
        assert detect_precision(1767830400000000) == "us"
        assert detect_precision(100000000000000000) == "us"

    def test_nanoseconds_precision(self):
        """测试纳秒级时间戳 (19位)"""
        assert detect_precision(1767830400000000000) == "ns"
        assert detect_precision(1767830400999999999) == "ns"

    def test_string_input(self):
        """测试字符串输入"""
        assert detect_precision("1767830400") == "s"
        assert detect_precision("1767830400000000000") == "ns"


class TestToNanoseconds:
    """测试 to_nanoseconds 函数"""

    def test_seconds_to_nanoseconds(self):
        """测试秒级转纳秒"""
        result = to_nanoseconds(1767830400, "s")
        assert result == 1767830400 * 1_000_000_000

    def test_milliseconds_to_nanoseconds(self):
        """测试毫秒级转纳秒"""
        result = to_nanoseconds(1767830400000, "ms")
        assert result == 1767830400000 * 1_000_000

    def test_microseconds_to_nanoseconds(self):
        """测试微秒级转纳秒"""
        result = to_nanoseconds(1767830400000000, "us")
        assert result == 1767830400000000 * 1_000

    def test_nanoseconds_passthrough(self):
        """测试纳秒级直接返回"""
        ns_ts = 1767830400000000000
        result = to_nanoseconds(ns_ts, "ns")
        assert result == ns_ts

    def test_auto_detect_precision(self):
        """测试自动检测精度"""
        assert to_nanoseconds(1767830400) == to_nanoseconds(1767830400, "s")
        assert to_nanoseconds(1767830400000) == to_nanoseconds(1767830400000, "ms")

    def test_invalid_input_raises(self):
        """测试无效输入抛出异常"""
        with pytest.raises(ValueError, match="无效的时间戳格式"):
            to_nanoseconds("invalid")
        with pytest.raises(ValueError, match="无效的时间戳格式"):
            to_nanoseconds(None)

    def test_unknown_precision_raises(self):
        """测试未知精度抛出异常"""
        with pytest.raises(ValueError, match="未知的精度类型"):
            to_nanoseconds(1767830400, "unknown")


class TestFromNanoseconds:
    """测试 from_nanoseconds 函数"""

    def test_nanoseconds_to_seconds(self):
        """测试纳秒转秒"""
        ns = 1767830400000000000
        assert from_nanoseconds(ns, "s") == 1767830400

    def test_nanoseconds_to_milliseconds(self):
        """测试纳秒转毫秒"""
        ns = 1767830400000000000
        assert from_nanoseconds(ns, "ms") == 1767830400000

    def test_nanoseconds_to_microseconds(self):
        """测试纳秒转微秒"""
        ns = 1767830400000000000
        assert from_nanoseconds(ns, "us") == 1767830400000000

    def test_nanoseconds_passthrough(self):
        """测试纳秒级直接返回"""
        ns = 1767830400000000000
        assert from_nanoseconds(ns, "ns") == ns

    def test_string_input(self):
        """测试字符串输入"""
        result = from_nanoseconds("1767830400000000000", "s")
        assert result == 1767830400

    def test_unknown_precision_raises(self):
        """测试未知精度抛出异常"""
        with pytest.raises(ValueError, match="未知的精度类型"):
            from_nanoseconds(1767830400000000000, "unknown")


class TestNormalizeToNanoseconds:
    """测试 normalize_to_nanoseconds 函数"""

    def test_normalize_seconds(self):
        """测试标准化秒级时间戳"""
        result = normalize_to_nanoseconds(1767830400)
        assert result == "1767830400000000000"

    def test_normalize_milliseconds(self):
        """测试标准化毫秒级时间戳"""
        result = normalize_to_nanoseconds(1767830400000)
        assert result == "1767830400000000000"

    def test_returns_string(self):
        """测试返回值是字符串"""
        result = normalize_to_nanoseconds(1767830400)
        assert isinstance(result, str)


class TestNanosecondsToDatetime:
    """测试 nanoseconds_to_datetime 函数"""

    def test_convert_to_datetime(self):
        """测试转换为datetime对象"""
        ns = 1767830400000000000  # 2026-01-08 00:00:00
        dt = nanoseconds_to_datetime(ns)
        assert dt.year == 2026
        assert dt.month == 1
        assert dt.day == 8

    def test_string_input(self):
        """测试字符串输入"""
        dt = nanoseconds_to_datetime("1767830400000000000")
        assert dt.year == 2026

    def test_epoch_start(self):
        """测试Unix纪元开始时间"""
        dt = nanoseconds_to_datetime(0)
        assert dt.year == 1970


class TestDatetimeToNanoseconds:
    """测试 datetime_to_nanoseconds 函数"""

    def test_datetime_to_nanoseconds(self):
        """测试datetime转换为纳秒"""
        dt = datetime(2026, 1, 8, 0, 0, 0)
        result = datetime_to_nanoseconds(dt)
        assert result == 1767830400000000000

    def test_roundtrip(self):
        """测试往返转换"""
        original_ns = 1767830400000000000
        dt = nanoseconds_to_datetime(original_ns)
        result = datetime_to_nanoseconds(dt)
        assert result == original_ns


class TestFormatNanoseconds:
    """测试 format_nanoseconds 函数"""

    def test_default_format(self):
        """测试默认格式化"""
        ns = 1767830400000000000
        result = format_nanoseconds(ns)
        assert result == "2026-01-08 00:00:00"

    def test_custom_format(self):
        """测试自定义格式化"""
        ns = 1767830400000000000
        result = format_nanoseconds(ns, "%Y-%m-%d")
        assert result == "2026-01-08"

    def test_string_input(self):
        """测试字符串输入"""
        result = format_nanoseconds("1767830400000000000")
        assert result == "2026-01-08 00:00:00"


class TestParseToNanoseconds:
    """测试 parse_to_nanoseconds 函数"""

    def test_parse_default_format(self):
        """测试解析默认格式"""
        result = parse_to_nanoseconds("2026-01-08 00:00:00")
        assert result == 1767830400000000000

    def test_parse_custom_format(self):
        """测试解析自定义格式"""
        result = parse_to_nanoseconds("2026-01-08", "%Y-%m-%d")
        assert result == 1767830400000000000

    def test_invalid_format_raises(self):
        """测试无效格式抛出异常"""
        with pytest.raises(ValueError):
            parse_to_nanoseconds("invalid-date", "%Y-%m-%d")


class TestMillisecondsNanosecondsConversion:
    """测试毫秒与纳秒之间的转换"""

    def test_ms_to_ns(self):
        """测试毫秒转纳秒"""
        result = milliseconds_to_nanoseconds(1000)
        assert result == 1000 * 1_000_000

    def test_ns_to_ms(self):
        """测试纳秒转毫秒"""
        ns = 1000000000000  # 1000000000000 ns = 1000000 ms
        result = nanoseconds_to_milliseconds(ns)
        assert result == 1000000

    def test_roundtrip(self):
        """测试往返转换"""
        original_ms = 1767830400000
        ns = milliseconds_to_nanoseconds(original_ms)
        result = nanoseconds_to_milliseconds(ns)
        assert result == original_ms


class TestBatchOperations:
    """测试批量转换操作"""

    def test_batch_to_nanoseconds(self):
        """测试批量转换为纳秒"""
        timestamps = [1767830400, 1767830401, 1767830402]
        results = batch_to_nanoseconds(timestamps, "s")
        assert len(results) == 3
        assert all(isinstance(r, int) for r in results)

    def test_batch_normalize_to_nanoseconds(self):
        """测试批量标准化"""
        timestamps = [1767830400, 1767830401]
        results = batch_normalize_to_nanoseconds(timestamps, "s")
        assert len(results) == 2
        assert all(isinstance(r, str) for r in results)


class TestValidation:
    """测试验证函数"""

    def test_is_valid_nanoseconds_true(self):
        """测试有效纳秒级时间戳"""
        assert is_valid_nanoseconds(1767830400000000000) is True
        assert is_valid_nanoseconds("1767830400000000000") is True

    def test_is_valid_nanoseconds_false(self):
        """测试无效时间戳"""
        assert is_valid_nanoseconds(123) is False
        assert is_valid_nanoseconds(999999999999999999999) is False
        assert is_valid_nanoseconds("invalid") is False

    def test_validate_nanoseconds_valid(self):
        """测试验证有效时间戳不抛异常"""
        validate_nanoseconds(1767830400000000000)
        validate_nanoseconds("1767830400000000000")

    def test_validate_nanoseconds_invalid(self):
        """测试验证无效时间戳抛出异常"""
        with pytest.raises(ValueError, match="timestamp 必须是有效的纳秒级时间戳"):
            validate_nanoseconds(123)
        with pytest.raises(ValueError):
            validate_nanoseconds("invalid")

    def test_validate_with_custom_field_name(self):
        """测试自定义字段名"""
        with pytest.raises(ValueError, match="created_at 必须是有效的"):
            validate_nanoseconds(123, "created_at")


class TestEdgeCases:
    """测试边界情况"""

    def test_zero_timestamp(self):
        """测试零时间戳"""
        assert detect_precision(0) == "s"
        assert to_nanoseconds(0) == 0
        assert nanoseconds_to_datetime(0).year == 1970

    def test_maximum_reasonable_timestamp(self):
        """测试最大合理时间戳"""
        max_ns = 4102444800000000000  # 2100-01-01
        assert is_valid_nanoseconds(max_ns)
        dt = nanoseconds_to_datetime(max_ns)
        assert dt.year == 2100

    def test_negative_timestamp(self):
        """测试负数时间戳"""
        assert is_valid_nanoseconds(-1) is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
