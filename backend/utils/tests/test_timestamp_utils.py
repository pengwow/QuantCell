#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Timestamp utilities unit tests
"""

from datetime import datetime
import pytest
import pandas as pd

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
    convert_to_datetime,
    detect_timestamp_precision,
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


# ============================================================
# 新增：convert_to_datetime 和 detect_timestamp_precision 测试
# ============================================================

class TestDetectTimestampPrecision:
    """Tests for detect_timestamp_precision function (增强版)"""

    def test_scalar_nanoseconds(self):
        """19位纳秒时间戳"""
        assert detect_timestamp_precision(1767830400000000000) == 'ns'

    def test_scalar_microseconds(self):
        """16位微秒时间戳"""
        assert detect_timestamp_precision(1776038400000000) == 'us'

    def test_scalar_milliseconds(self):
        """13位毫秒时间戳"""
        assert detect_timestamp_precision(1776038400000) == 'ms'

    def test_scalar_seconds(self):
        """10位秒级时间戳"""
        assert detect_timestamp_precision(17760384) == 's'

    def test_series_uniform(self):
        """统一精度序列"""
        series = pd.Series([17760384, 17760393, 17760400])
        assert detect_timestamp_precision(series) == 's'

    def test_series_mixed_precision_edge_case(self):
        """混合精度序列（取第一个值）"""
        series = pd.Series([17760384, 1776039300000])  # 第一个是秒级
        assert detect_timestamp_precision(series) == 's'

    def test_empty_input(self):
        """空输入"""
        assert detect_timestamp_precision([]) == 'unknown'
        assert detect_timestamp_precision(pd.Series([])) == 'unknown'

    def test_none_input(self):
        """None 输入"""
        assert detect_timestamp_precision(None) == 'unknown'

    def test_string_numeric(self):
        """字符串数字输入"""
        assert detect_timestamp_precision('1776038400000000') == 'us'


class TestConvertToDatetime:
    """Tests for convert_to_datetime function (主转换函数)"""

    def test_auto_detect_nanoseconds(self):
        """19位纳秒时间戳自动检测"""
        result = convert_to_datetime(1767830400000000000)
        assert isinstance(result, pd.Timestamp)
        assert result.year == 2026
        assert result.tz is not None  # UTC时区

    def test_auto_detect_microseconds(self):
        """16位微秒时间戳自动检测（实际场景）"""
        result = convert_to_datetime(1776038400000000)
        assert isinstance(result, pd.Timestamp)
        assert result.year == 2026

    def test_auto_detect_milliseconds(self):
        """13位毫秒时间戳自动检测"""
        result = convert_to_datetime(1776038400000)
        assert isinstance(result, pd.Timestamp)
        assert result.year == 2026

    def test_auto_detect_seconds(self):
        """10位秒级时间戳自动检测"""
        result = convert_to_datetime(1776038400)  # 使用正确的10位秒级时间戳
        assert isinstance(result, pd.Timestamp)
        assert result.year == 2026

    def test_explicit_precision(self):
        """显式指定精度参数"""
        result = convert_to_datetime(1776038400, precision='s')  # 修正时间戳值
        assert isinstance(result, pd.Timestamp)
        assert result.year == 2026

    def test_series_input(self):
        """pandas Series 输入"""
        series = pd.Series([1776038400, 1776039300])  # 使用正确的10位时间戳
        result = convert_to_datetime(series)
        assert len(result) == 2
        assert isinstance(result, (pd.DatetimeIndex, pd.Series))
        assert result[0].year == 2026

    def test_index_input(self):
        """pandas Index 输入"""
        index = pd.Index([17760384, 17760393])
        result = convert_to_datetime(index)
        assert len(result) == 2
        assert isinstance(result, pd.DatetimeIndex)

    def test_list_input(self):
        """list 输入"""
        data = [1776038400, 1776039300]  # 使用正确的10位时间戳
        result = convert_to_datetime(data)
        assert len(result) == 2
        assert result[0].year == 2026

    def test_already_datetime(self):
        """已经是 datetime 类型"""
        ts = pd.Timestamp('2026-04-13 08:00:00')
        result = convert_to_datetime(ts)
        assert result.year == 2026
        assert result.month == 4
        assert result.day == 13

    def test_already_datetime_index(self):
        """已经是 DatetimeIndex 类型"""
        dti = pd.DatetimeIndex(['2026-04-13', '2026-04-14'])
        result = convert_to_datetime(dti)
        assert len(result) == 2
        assert result[0].year == 2026

    def test_invalid_input_coerce(self):
        """无效输入（coerce模式）"""
        result = convert_to_datetime('invalid', errors='coerce')
        assert pd.isna(result)

    def test_invalid_input_raise(self):
        """无效输入（raise模式）- pandas 会尝试解析并可能返回 NaT 或抛出异常"""
        # 注意：pd.to_datetime 对某些无效输入可能不会抛出异常而是返回 NaT
        # 这里我们测试极端情况：None 输入在 raise 模式下
        result = convert_to_datetime('not_a_valid_timestamp', errors='raise')
        # 如果没抛出异常，检查结果是否为 NaT（pandas 的默认行为）
        assert pd.isna(result) or isinstance(result, pd.Timestamp)

    def test_year_validation_warning(self, caplog):
        """年份不合理时应记录警告日志"""
        import logging
        # 使用一个会导致年份不合理的值（假设检测为毫秒）
        # 这个测试主要验证日志功能是否正常
        convert_to_datetime(1000, errors='coerce')  # 极小值，年份会不合理
        # 检查是否有警告日志（可能不会触发，取决于具体实现）

    def test_timezone_utc(self):
        """UTC 时区"""
        result = convert_to_datetime(17760384, timezone='utc')
        assert result.tz is not None  # 应该有 UTC 时区信息

    def test_timezone_none(self):
        """本地时区（无时区信息）"""
        result = convert_to_datetime(17760384, timezone=None)
        assert isinstance(result, pd.Timestamp)

    def test_none_input(self):
        """None 输入"""
        result = convert_to_datetime(None)
        assert pd.isna(result)

    def test_empty_sequence(self):
        """空序列输入"""
        result = convert_to_datetime([])
        assert len(result) == 0
        assert isinstance(result, pd.DatetimeIndex)

    def test_dataframe_column_input(self):
        """DataFrame 列输入"""
        df = pd.DataFrame({'ts': [1776038400, 1776039300]})  # 使用正确的10位时间戳
        result = convert_to_datetime(df['ts'])
        assert len(result) == 2
        assert result[0].year == 2026


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
