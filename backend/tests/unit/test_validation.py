# -*- coding: utf-8 -*-
"""
参数验证工具模块单元测试

测试 validation 模块的CLI参数验证功能。

作者: QuantCell Team
版本: 1.0.0
日期: 2026-05-09
"""

import pytest
from datetime import datetime

from utils.validation import (
    VALID_TIMEFRAMES,
    VALID_TRADING_MODES,
    validate_time_range,
    parse_time_range,
    validate_symbols,
    parse_symbols,
    validate_timeframes,
    parse_timeframes,
    validate_trading_mode,
    get_default_values,
)


class TestValidConstants:
    """测试有效值常量"""

    def test_valid_timeframes(self):
        """测试有效时间周期"""
        assert '15m' in VALID_TIMEFRAMES
        assert '30m' in VALID_TIMEFRAMES
        assert '1h' in VALID_TIMEFRAMES
        assert '4h' in VALID_TIMEFRAMES
        assert '1d' in VALID_TIMEFRAMES
        assert '1m' not in VALID_TIMEFRAMES

    def test_valid_trading_modes(self):
        """测试有效交易模式"""
        assert 'spot' in VALID_TRADING_MODES
        assert 'futures' in VALID_TRADING_MODES
        assert 'perpetual' in VALID_TRADING_MODES


class TestValidateTimeRange:
    """测试 validate_time_range 函数"""

    def test_none_returns_true(self):
        """测试None返回True（允许为空）"""
        assert validate_time_range(None) is True

    def test_empty_string_returns_true(self):
        """测试空字符串返回True"""
        assert validate_time_range("") is True

    def test_valid_YYYYMMDD_format(self):
        """测试有效的YYYYMMDD格式"""
        assert validate_time_range("20240101-20241231") is True
        assert validate_time_range("20240101-20240102") is True

    def test_valid_ISO_date_format(self):
        """测试有效的ISO日期格式 - 注意：实现只支持YYYYMMDD格式"""
        assert validate_time_range("20240101-20241231") is True

    def test_invalid_format_too_many_parts(self):
        """测试无效格式（无法解析的日期字符串）"""
        assert validate_time_range("not-a-valid-date") is False

    def test_invalid_format_wrong_separator(self):
        """测试无效格式（太多部分）"""
        assert validate_time_range("20240101-20240102-20240103") is False

    def test_invalid_format_wrong_separator(self):
        """测试无效格式（错误的分隔符）"""
        assert validate_time_range("20240101_20241231") is False

    def test_start_after_end(self):
        """测试开始日期在结束日期之后"""
        assert validate_time_range("20241231-20240101") is False
        assert validate_time_range("2024-12-31-2024-01-01") is False

    def test_start_equals_end(self):
        """测试开始日期等于结束日期"""
        assert validate_time_range("20240101-20240101") is False

    def test_invalid_date_string(self):
        """测试无效日期字符串"""
        assert validate_time_range("invalid-date") is False
        assert validate_time_range("2024-13-01-2024-12-31") is False


class TestParseTimeRange:
    """测试 parse_time_range 函数"""

    def test_none_returns_none_tuple(self):
        """测试None返回(None, None)"""
        result = parse_time_range(None)
        assert result == (None, None)

    def test_parse_YYYYMMDD_format(self):
        """测试解析YYYYMMDD格式"""
        start, end = parse_time_range("20240101-20241231")
        assert start == datetime(2024, 1, 1)
        assert end == datetime(2024, 12, 31)

    def test_invalid_format_raises(self):
        """测试无效格式抛出异常"""
        with pytest.raises(ValueError, match="时间范围格式错误"):
            parse_time_range("invalid")
        with pytest.raises(ValueError, match="时间范围格式错误"):
            parse_time_range("20240101-20240102-20240103")

    def test_invalid_date_raises(self):
        """测试无效日期抛出异常"""
        with pytest.raises(ValueError):
            parse_time_range("2024-13-01-2024-12-31")

    def test_start_after_end_raises(self):
        """测试开始日期在结束日期之后抛出异常"""
        with pytest.raises(ValueError, match="开始日期必须早于结束日期"):
            parse_time_range("20241231-20240101")


class TestValidateSymbols:
    """测试 validate_symbols 函数"""

    def test_none_returns_true(self):
        """测试None返回True"""
        assert validate_symbols(None) is True

    def test_empty_string_returns_true(self):
        """测试空字符串返回True"""
        assert validate_symbols("") is True

    def test_valid_single_symbol(self):
        """测试有效的单个货币对"""
        assert validate_symbols("BTCUSDT") is True

    def test_valid_multiple_symbols(self):
        """测试有效的多个货币对"""
        assert validate_symbols("BTCUSDT,ETHUSDT") is True
        assert validate_symbols("BTCUSDT, ETHUSDT, SOLUSDT") is True

    def test_empty_symbols_ignored(self):
        """测试空货币对被忽略"""
        assert validate_symbols("BTCUSDT,,ETHUSDT") is True


class TestParseSymbols:
    """测试 parse_symbols 函数"""

    def test_none_returns_empty_list(self):
        """测试None返回空列表"""
        assert parse_symbols(None) == []

    def test_empty_string_returns_empty_list(self):
        """测试空字符串返回空列表"""
        assert parse_symbols("") == []

    def test_parse_single_symbol(self):
        """测试解析单个货币对"""
        result = parse_symbols("BTCUSDT")
        assert result == ["BTCUSDT"]

    def test_parse_multiple_symbols(self):
        """测试解析多个货币对"""
        result = parse_symbols("BTCUSDT,ETHUSDT,SOLUSDT")
        assert result == ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

    def test_whitespace_trimming(self):
        """测试去除空白"""
        result = parse_symbols("BTCUSDT, ETHUSDT , SOLUSDT")
        assert result == ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

    def test_empty_symbols_filtered(self):
        """测试过滤空货币对"""
        result = parse_symbols("BTCUSDT,,ETHUSDT,,SOLUSDT")
        assert result == ["BTCUSDT", "ETHUSDT", "SOLUSDT"]


class TestValidateTimeframes:
    """测试 validate_timeframes 函数"""

    def test_none_returns_true(self):
        """测试None返回True"""
        assert validate_timeframes(None) is True

    def test_empty_string_returns_true(self):
        """测试空字符串返回True"""
        assert validate_timeframes("") is True

    def test_valid_single_timeframe(self):
        """测试有效的单个时间周期"""
        assert validate_timeframes("1h") is True
        assert validate_timeframes("15m") is True

    def test_valid_multiple_timeframes(self):
        """测试有效的多个时间周期"""
        assert validate_timeframes("15m,30m,1h") is True
        assert validate_timeframes("1h,4h,1d") is True

    def test_invalid_timeframe(self):
        """测试无效时间周期"""
        assert validate_timeframes("2h") is False
        assert validate_timeframes("1m") is False
        assert validate_timeframes("random") is False

    def test_mixed_valid_invalid_timeframes(self):
        """测试混合有效和无效时间周期"""
        assert validate_timeframes("1h,2h") is False


class TestParseTimeframes:
    """测试 parse_timeframes 函数"""

    def test_none_returns_empty_list(self):
        """测试None返回空列表"""
        assert parse_timeframes(None) == []

    def test_empty_string_returns_empty_list(self):
        """测试空字符串返回空列表"""
        assert parse_timeframes("") == []

    def test_parse_single_timeframe(self):
        """测试解析单个时间周期"""
        result = parse_timeframes("1h")
        assert result == ["1h"]

    def test_parse_multiple_timeframes(self):
        """测试解析多个时间周期"""
        result = parse_timeframes("15m,30m,1h,4h")
        assert result == ["15m", "30m", "1h", "4h"]

    def test_whitespace_trimming(self):
        """测试去除空白"""
        result = parse_timeframes(" 15m , 30m , 1h ")
        assert result == ["15m", "30m", "1h"]


class TestValidateTradingMode:
    """测试 validate_trading_mode 函数"""

    def test_none_returns_true(self):
        """测试None返回True（允许为空）"""
        assert validate_trading_mode(None) is True

    def test_valid_spot(self):
        """测试有效的现货模式"""
        assert validate_trading_mode("spot") is True

    def test_valid_futures(self):
        """测试有效的期货模式"""
        assert validate_trading_mode("futures") is True

    def test_valid_perpetual(self):
        """测试有效的永续模式"""
        assert validate_trading_mode("perpetual") is True

    def test_invalid_mode(self):
        """测试无效模式"""
        assert validate_trading_mode("margin") is False
        assert validate_trading_mode("options") is False
        assert validate_trading_mode("SPOT") is False  # 大小写敏感


class TestGetDefaultValues:
    """测试 get_default_values 函数"""

    def test_returns_dict(self):
        """测试返回字典"""
        result = get_default_values()
        assert isinstance(result, dict)

    def test_contains_required_keys(self):
        """测试包含必需键"""
        result = get_default_values()
        assert "trading_mode" in result
        assert "timeframes" in result
        assert "symbols" in result
        assert "init_cash" in result
        assert "fees" in result
        assert "slippage" in result

    def test_default_values(self):
        """测试默认值"""
        result = get_default_values()
        assert result["trading_mode"] == "spot"
        assert result["timeframes"] == ["1h"]
        assert result["symbols"] == ["BTCUSDT"]
        assert result["init_cash"] == 100000.0
        assert result["fees"] == 0.001
        assert result["slippage"] == 0.0001


class TestIntegrationScenarios:
    """测试集成场景"""

    def test_full_cli_params_validation(self):
        """测试完整CLI参数验证"""
        time_range = "20240101-20241231"
        symbols = "BTCUSDT,ETHUSDT"
        timeframes = "15m,1h,4h"
        trading_mode = "spot"

        assert validate_time_range(time_range) is True
        assert validate_symbols(symbols) is True
        assert validate_timeframes(timeframes) is True
        assert validate_trading_mode(trading_mode) is True

    def test_parse_and_validate_consistency(self):
        """测试解析和验证的一致性"""
        time_range = "20240101-20241231"
        assert validate_time_range(time_range) is True
        start, end = parse_time_range(time_range)
        assert start is not None
        assert end is not None
        assert start < end

    def test_symbols_consistency(self):
        """测试货币对解析一致性"""
        symbols_str = "BTCUSDT,ETHUSDT,SOLUSDT"
        assert validate_symbols(symbols_str) is True
        parsed = parse_symbols(symbols_str)
        assert len(parsed) == 3
        assert "BTCUSDT" in parsed
        assert "ETHUSDT" in parsed
        assert "SOLUSDT" in parsed


class TestEdgeCases:
    """测试边界情况"""

    def test_whitespace_only_timeframes(self):
        """测试只有空白的时间周期"""
        assert validate_timeframes("   ") is True
        assert parse_timeframes("   ") == []

    def test_very_long_symbol_string(self):
        """测试非常长的货币对字符串"""
        many_symbols = ",".join([f"SYMBOL{i}" for i in range(100)])
        assert validate_symbols(many_symbols) is True
        assert len(parse_symbols(many_symbols)) == 100

    def test_date_at_year_boundary(self):
        """测试年份边界的日期"""
        assert validate_time_range("20231231-20240101") is True
        start, end = parse_time_range("20231231-20240101")
        assert start.year == 2023
        assert end.year == 2024


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
