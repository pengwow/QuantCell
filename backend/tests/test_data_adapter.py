# -*- coding: utf-8 -*-
"""
数据适配器单元测试

测试数据适配器的核心功能，包括:
- kline_to_bars 函数
- load_bars_from_csv 函数
- load_bars_from_parquet 函数
- 数据验证逻辑
- 错误处理

作者: QuantCell Team
版本: 1.0.0
日期: 2026-02-23
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import numpy as np
import pandas as pd
import pytest

from nautilus_trader.model.data import Bar, BarType, BarSpecification
from nautilus_trader.model.enums import BarAggregation, PriceType
from nautilus_trader.model.instruments import CurrencyPair
from nautilus_trader.model.objects import Price, Quantity

from backend.backtest.adapters.data_adapter import (
    COMMON_PAIRS,
    _ms_to_ns,
    _validate_kline_df,
    _get_timestamp_ns,
    _standardize_dataframe,
    _create_bar_type,
    kline_to_quote_ticks,
    kline_to_trade_ticks,
    kline_to_bars,
    create_instrument,
    register_custom_pair,
    load_bars_from_csv,
    load_bars_from_parquet,
    create_bar_type_from_string,
    get_bar_aggregation_from_string,
)


# =============================================================================
# 测试固件 (Fixtures)
# =============================================================================

@pytest.fixture
def sample_kline_df():
    """返回示例 K 线 DataFrame"""
    return pd.DataFrame({
        "timestamp": pd.date_range("2023-01-01", periods=100, freq="1min"),
        "open": [50000.0 + i * 10 for i in range(100)],
        "high": [50100.0 + i * 10 for i in range(100)],
        "low": [49900.0 + i * 10 for i in range(100)],
        "close": [50050.0 + i * 10 for i in range(100)],
        "volume": [100.0 + i for i in range(100)],
    })


@pytest.fixture
def sample_kline_df_with_index():
    """返回以时间为索引的 K 线 DataFrame"""
    df = pd.DataFrame({
        "open": [50000.0 + i * 10 for i in range(100)],
        "high": [50100.0 + i * 10 for i in range(100)],
        "low": [49900.0 + i * 10 for i in range(100)],
        "close": [50050.0 + i * 10 for i in range(100)],
        "volume": [100.0 + i for i in range(100)],
    }, index=pd.date_range("2023-01-01", periods=100, freq="1min"))
    return df


@pytest.fixture
def sample_instrument():
    """返回一个真实的 BTCUSDT 交易品种"""
    return create_instrument("BTCUSDT", venue="BINANCE")


@pytest.fixture
def sample_csv_file(tmp_path, sample_kline_df):
    """创建临时 CSV 文件并返回路径"""
    csv_path = tmp_path / "test_data.csv"
    sample_kline_df.to_csv(csv_path, index=False)
    return csv_path


@pytest.fixture
def sample_parquet_file(tmp_path, sample_kline_df):
    """创建临时 Parquet 文件并返回路径"""
    parquet_path = tmp_path / "test_data.parquet"
    sample_kline_df.to_parquet(parquet_path, index=False)
    return parquet_path


# =============================================================================
# 工具函数测试
# =============================================================================

class TestUtilityFunctions:
    """测试工具函数"""

    def test_ms_to_ns(self):
        """测试毫秒到纳秒转换"""
        ms = 1704067200000  # 2024-01-01 00:00:00 UTC in ms
        ns = _ms_to_ns(ms)
        expected_ns = ms * 1_000_000
        assert ns == expected_ns

    def test_ms_to_ns_with_int_conversion(self):
        """测试毫秒到纳秒的类型转换"""
        result = _ms_to_ns(1000)
        assert isinstance(result, int)
        assert result == 1000_000_000


# =============================================================================
# 数据验证测试
# =============================================================================

class TestDataValidation:
    """测试数据验证功能"""

    def test_validate_kline_df_success(self, sample_kline_df):
        """测试验证有效数据"""
        # 不应抛出异常
        _validate_kline_df(sample_kline_df)

    def test_validate_kline_df_missing_columns(self):
        """测试缺少必要列时抛出异常"""
        df = pd.DataFrame({
            "open": [1, 2, 3],
            "close": [2, 3, 4],
        })

        with pytest.raises(ValueError, match="缺少必要列"):
            _validate_kline_df(df)

    def test_validate_kline_df_empty(self):
        """测试空 DataFrame 抛出异常"""
        df = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        with pytest.raises(ValueError, match="数据为空"):
            _validate_kline_df(df)

    def test_validate_kline_df_with_null_values(self):
        """测试包含空值的数据抛出异常"""
        df = pd.DataFrame({
            "open": [1.0, 2.0, None],
            "high": [2.0, 3.0, 4.0],
            "low": [0.5, 1.5, 2.5],
            "close": [1.5, 2.5, 3.5],
            "volume": [100, 200, 300],
        })

        with pytest.raises(ValueError, match="包含空值"):
            _validate_kline_df(df)


# =============================================================================
# 时间戳处理测试
# =============================================================================

class TestTimestampHandling:
    """测试时间戳处理功能"""

    def test_get_timestamp_ns_from_timestamp_column(self):
        """测试从 timestamp 列获取纳秒时间戳"""
        row = pd.Series({
            "timestamp": 1704067200000,  # ms
            "open": 50000,
        })
        df = pd.DataFrame()  # 仅用于参数

        result = _get_timestamp_ns(row, df)
        assert result == 1704067200000 * 1_000_000

    def test_get_timestamp_ns_from_ns_timestamp(self):
        """测试纳秒级时间戳"""
        row = pd.Series({
            "timestamp": 1704067200000000000,  # ns
        })
        df = pd.DataFrame()

        result = _get_timestamp_ns(row, df)
        assert result == 1704067200000000000

    def test_get_timestamp_ns_from_second_timestamp(self):
        """测试秒级时间戳"""
        row = pd.Series({
            "timestamp": 1704067200,  # seconds
        })
        df = pd.DataFrame()

        result = _get_timestamp_ns(row, df)
        assert result == 1704067200 * 1_000_000_000

    def test_get_timestamp_ns_from_datetime_index(self):
        """测试从 DatetimeIndex 获取时间戳"""
        df = pd.DataFrame({
            "open": [50000],
        }, index=pd.to_datetime(["2024-01-01 00:00:00"]))

        row = df.iloc[0]
        result = _get_timestamp_ns(row, df)
        assert isinstance(result, int)
        assert result > 0


# =============================================================================
# DataFrame 标准化测试
# =============================================================================

class TestStandardizeDataFrame:
    """测试 DataFrame 标准化功能"""

    def test_standardize_dataframe_success(self, sample_kline_df):
        """测试成功标准化 DataFrame"""
        result = _standardize_dataframe(sample_kline_df)

        assert "open" in result.columns
        assert "high" in result.columns
        assert "low" in result.columns
        assert "close" in result.columns
        assert "volume" in result.columns
        assert result.index.name == "timestamp"

    def test_standardize_dataframe_with_column_mapping(self):
        """测试使用列名映射标准化"""
        df = pd.DataFrame({
            "ts": pd.date_range("2023-01-01", periods=10),
            "o": [1.0] * 10,
            "h": [2.0] * 10,
            "l": [0.5] * 10,
            "c": [1.5] * 10,
            "v": [100] * 10,
        })

        mapping = {"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"}
        result = _standardize_dataframe(df, column_mapping=mapping, timestamp_column="ts")

        assert "open" in result.columns
        assert result.index.name == "timestamp"

    def test_standardize_dataframe_missing_required_columns(self):
        """测试缺少必要列时抛出异常"""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2023-01-01", periods=10),
            "open": [1.0] * 10,
            "close": [1.5] * 10,
        })

        with pytest.raises(ValueError, match="缺少必要列"):
            _standardize_dataframe(df)

    def test_standardize_dataframe_invalid_high_low(self):
        """测试 high < low 时抛出异常"""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2023-01-01", periods=10),
            "open": [1.0] * 10,
            "high": [0.5] * 10,  # high < low
            "low": [2.0] * 10,
            "close": [1.5] * 10,
            "volume": [100] * 10,
        })

        with pytest.raises(ValueError, match="high < low"):
            _standardize_dataframe(df)

    def test_standardize_dataframe_adds_volume_if_missing(self):
        """测试缺少 volume 列时自动添加"""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2023-01-01", periods=10),
            "open": [1.0] * 10,
            "high": [2.0] * 10,
            "low": [0.5] * 10,
            "close": [1.5] * 10,
        })

        result = _standardize_dataframe(df)
        assert "volume" in result.columns
        assert (result["volume"] == 0.0).all()


# =============================================================================
# BarType 创建测试
# =============================================================================

class TestBarTypeCreation:
    """测试 BarType 创建功能"""

    def test_create_bar_type(self, sample_instrument):
        """测试创建 BarType"""
        bar_type = _create_bar_type(
            sample_instrument,
            BarAggregation.MINUTE,
            5,
            PriceType.LAST,
        )

        assert bar_type is not None
        assert isinstance(bar_type, BarType)

    def test_create_bar_type_from_string_success(self):
        """测试从字符串创建 BarType"""
        result = create_bar_type_from_string("BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL")
        assert result is not None
        assert isinstance(result, BarType)

    def test_create_bar_type_from_string_invalid(self):
        """测试无效字符串时抛出异常"""
        with pytest.raises(ValueError, match="无效的 BarType 字符串"):
            create_bar_type_from_string("invalid-format")

    def test_get_bar_aggregation_from_string(self):
        """测试从字符串获取 BarAggregation"""
        assert get_bar_aggregation_from_string("tick") == BarAggregation.TICK
        assert get_bar_aggregation_from_string("second") == BarAggregation.SECOND
        assert get_bar_aggregation_from_string("minute") == BarAggregation.MINUTE
        assert get_bar_aggregation_from_string("hour") == BarAggregation.HOUR
        assert get_bar_aggregation_from_string("day") == BarAggregation.DAY
        assert get_bar_aggregation_from_string("week") == BarAggregation.WEEK
        assert get_bar_aggregation_from_string("month") == BarAggregation.MONTH

    def test_get_bar_aggregation_from_string_case_insensitive(self):
        """测试大小写不敏感"""
        assert get_bar_aggregation_from_string("MINUTE") == BarAggregation.MINUTE
        assert get_bar_aggregation_from_string("Minute") == BarAggregation.MINUTE

    def test_get_bar_aggregation_from_string_invalid(self):
        """测试无效字符串时抛出异常"""
        with pytest.raises(ValueError, match="无效的聚合类型"):
            get_bar_aggregation_from_string("invalid")


# =============================================================================
# kline_to_bars 测试
# =============================================================================

class TestKlineToBars:
    """测试 kline_to_bars 函数"""

    def test_kline_to_bars_success(self, sample_kline_df_with_index, sample_instrument):
        """测试成功转换 K 线到 Bars"""
        bars = kline_to_bars(sample_kline_df_with_index, sample_instrument)

        assert len(bars) == 100
        assert isinstance(bars[0], Bar)

    def test_kline_to_bars_empty_dataframe(self, sample_instrument):
        """测试空 DataFrame 抛出异常"""
        empty_df = pd.DataFrame()

        with pytest.raises(ValueError, match="输入的 DataFrame 为空"):
            kline_to_bars(empty_df, sample_instrument)

    def test_kline_to_bars_with_custom_params(self, sample_kline_df_with_index, sample_instrument):
        """测试使用自定义参数转换"""
        bars = kline_to_bars(
            sample_kline_df_with_index,
            sample_instrument,
            aggregation=BarAggregation.HOUR,
            step=4,
            price_type=PriceType.BID,
        )

        assert len(bars) == 100
        assert isinstance(bars[0], Bar)

    def test_kline_to_bars_with_column_mapping(self, sample_instrument):
        """测试使用列名映射"""
        df = pd.DataFrame({
            "ts": pd.date_range("2023-01-01", periods=10),
            "o": [1.0] * 10,
            "h": [2.0] * 10,
            "l": [0.5] * 10,
            "c": [1.5] * 10,
            "v": [100] * 10,
        })

        mapping = {"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"}
        bars = kline_to_bars(df, sample_instrument, column_mapping=mapping, timestamp_column="ts")

        assert bars is not None
        assert len(bars) == 10

    def test_kline_to_bars_error_handling(self, sample_instrument):
        """测试错误处理"""
        # 使用无效数据触发错误
        invalid_df = pd.DataFrame({
            "timestamp": pd.date_range("2023-01-01", periods=10),
            "open": [1.0] * 10,
            "high": [0.5] * 10,  # high < low 会触发错误
            "low": [2.0] * 10,
            "close": [1.5] * 10,
            "volume": [100] * 10,
        })

        with pytest.raises(Exception):
            kline_to_bars(invalid_df, sample_instrument)


# =============================================================================
# kline_to_quote_ticks 测试
# =============================================================================

class TestKlineToQuoteTicks:
    """测试 kline_to_quote_ticks 函数"""

    def test_kline_to_quote_ticks_success(self, sample_kline_df_with_index, sample_instrument):
        """测试成功转换 K 线到 QuoteTicks"""
        ticks = kline_to_quote_ticks(sample_kline_df_with_index, sample_instrument)

        assert len(ticks) == len(sample_kline_df_with_index)
        assert ticks[0].instrument_id == sample_instrument.id

    def test_kline_to_quote_ticks_with_offsets(self, sample_kline_df_with_index, sample_instrument):
        """测试使用价格偏移量"""
        bid_offset = 10.0
        ask_offset = 10.0

        ticks = kline_to_quote_ticks(
            sample_kline_df_with_index,
            sample_instrument,
            bid_offset=bid_offset,
            ask_offset=ask_offset,
        )

        # 验证价格偏移
        first_close = float(sample_kline_df_with_index.iloc[0]["close"])
        expected_bid = first_close - bid_offset
        expected_ask = first_close + ask_offset

        assert float(ticks[0].bid_price) == pytest.approx(expected_bid, abs=0.01)
        assert float(ticks[0].ask_price) == pytest.approx(expected_ask, abs=0.01)

    def test_kline_to_quote_ticks_invalid_data(self, sample_instrument):
        """测试无效数据抛出异常"""
        invalid_df = pd.DataFrame({
            "open": [1.0],
            "close": [1.5],
        })

        with pytest.raises(ValueError, match="缺少必要列"):
            kline_to_quote_ticks(invalid_df, sample_instrument)


# =============================================================================
# kline_to_trade_ticks 测试
# =============================================================================

class TestKlineToTradeTicks:
    """测试 kline_to_trade_ticks 函数"""

    def test_kline_to_trade_ticks_success(self, sample_kline_df_with_index, sample_instrument):
        """测试成功转换 K 线到 TradeTicks"""
        ticks = kline_to_trade_ticks(sample_kline_df_with_index, sample_instrument)

        assert len(ticks) == len(sample_kline_df_with_index)
        assert ticks[0].instrument_id == sample_instrument.id

    def test_kline_to_trade_ticks_buy_side(self, sample_kline_df_with_index, sample_instrument):
        """测试买入方向"""
        from nautilus_trader.model.enums import AggressorSide

        ticks = kline_to_trade_ticks(sample_kline_df_with_index, sample_instrument, trade_side="BUY")

        assert ticks[0].aggressor_side == AggressorSide.BUYER

    def test_kline_to_trade_ticks_sell_side(self, sample_kline_df_with_index, sample_instrument):
        """测试卖出方向"""
        from nautilus_trader.model.enums import AggressorSide

        ticks = kline_to_trade_ticks(sample_kline_df_with_index, sample_instrument, trade_side="SELL")

        assert ticks[0].aggressor_side == AggressorSide.SELLER


# =============================================================================
# 创建 Instrument 测试
# =============================================================================

class TestCreateInstrument:
    """测试 create_instrument 函数"""

    def test_create_instrument_btcusdt(self):
        """测试创建 BTCUSDT 交易品种"""
        instrument = create_instrument("BTCUSDT")

        assert instrument is not None
        assert "BTC" in str(instrument.id)
        assert "USDT" in str(instrument.id)
        assert instrument.price_precision == 2
        assert instrument.size_precision == 6

    def test_create_instrument_ethusdt(self):
        """测试创建 ETHUSDT 交易品种"""
        instrument = create_instrument("ETHUSDT")

        assert instrument is not None
        assert instrument.price_precision == 2
        assert instrument.size_precision == 5

    def test_create_instrument_custom_precision(self):
        """测试自定义精度"""
        instrument = create_instrument("BTCUSDT", price_precision=4, size_precision=8)

        assert instrument.price_precision == 4
        assert instrument.size_precision == 8

    def test_create_instrument_unknown_symbol(self):
        """测试未知交易对符号"""
        instrument = create_instrument("UNKNOWNUSDT")

        assert instrument is not None
        # 应该使用默认配置

    def test_create_instrument_custom_venue(self):
        """测试自定义交易所"""
        instrument = create_instrument("BTCUSDT", venue="COINBASE")

        assert "COINBASE" in str(instrument.id)


# =============================================================================
# 注册自定义交易对测试
# =============================================================================

class TestRegisterCustomPair:
    """测试 register_custom_pair 函数"""

    def test_register_custom_pair_success(self):
        """测试成功注册自定义交易对"""
        register_custom_pair("PEPEUSDT", "PEPE", "USDT", 10, 0)

        assert "PEPEUSDT" in COMMON_PAIRS
        assert COMMON_PAIRS["PEPEUSDT"]["base"] == "PEPE"
        assert COMMON_PAIRS["PEPEUSDT"]["quote"] == "USDT"
        assert COMMON_PAIRS["PEPEUSDT"]["price_precision"] == 10
        assert COMMON_PAIRS["PEPEUSDT"]["size_precision"] == 0

        # 清理
        del COMMON_PAIRS["PEPEUSDT"]

    def test_register_custom_pair_case_insensitive(self):
        """测试大小写不敏感"""
        register_custom_pair("testusdt", "TEST", "USDT", 2, 6)

        assert "TESTUSDT" in COMMON_PAIRS

        # 清理
        del COMMON_PAIRS["TESTUSDT"]


# =============================================================================
# 从 CSV 加载测试
# =============================================================================

class TestLoadBarsFromCsv:
    """测试 load_bars_from_csv 函数"""

    def test_load_bars_from_csv_success(self, sample_csv_file, sample_instrument):
        """测试成功从 CSV 加载 Bars"""
        bars = load_bars_from_csv(sample_csv_file, sample_instrument)

        assert len(bars) == 100
        assert isinstance(bars[0], Bar)

    def test_load_bars_from_csv_file_not_found(self, sample_instrument):
        """测试文件不存在时抛出异常"""
        with pytest.raises(FileNotFoundError, match="CSV 文件不存在"):
            load_bars_from_csv("/nonexistent/path/file.csv", sample_instrument)

    def test_load_bars_from_csv_with_custom_sep(self, tmp_path, sample_instrument):
        """测试使用自定义分隔符"""
        # 创建分号分隔的 CSV
        csv_path = tmp_path / "semicolon.csv"
        df = pd.DataFrame({
            "timestamp": pd.date_range("2023-01-01", periods=10),
            "open": [1.0] * 10,
            "high": [2.0] * 10,
            "low": [0.5] * 10,
            "close": [1.5] * 10,
            "volume": [100] * 10,
        })
        df.to_csv(csv_path, index=False, sep=";")

        bars = load_bars_from_csv(csv_path, sample_instrument, sep=";")
        assert bars is not None
        assert len(bars) == 10

    def test_load_bars_from_csv_no_header(self, tmp_path, sample_instrument):
        """测试无 header 的 CSV"""
        csv_path = tmp_path / "no_header.csv"
        df = pd.DataFrame({
            "timestamp": pd.date_range("2023-01-01", periods=10),
            "open": [1.0] * 10,
            "high": [2.0] * 10,
            "low": [0.5] * 10,
            "close": [1.5] * 10,
            "volume": [100] * 10,
        })
        df.to_csv(csv_path, index=False, header=False)

        bars = load_bars_from_csv(
            csv_path,
            sample_instrument,
            header=None,
            names=["timestamp", "open", "high", "low", "close", "volume"],
        )
        assert bars is not None
        assert len(bars) == 10


# =============================================================================
# 从 Parquet 加载测试
# =============================================================================

class TestLoadBarsFromParquet:
    """测试 load_bars_from_parquet 函数"""

    def test_load_bars_from_parquet_success(self, sample_parquet_file, sample_instrument):
        """测试成功从 Parquet 加载 Bars"""
        bars = load_bars_from_parquet(sample_parquet_file, sample_instrument)

        assert len(bars) == 100
        assert isinstance(bars[0], Bar)

    def test_load_bars_from_parquet_file_not_found(self, sample_instrument):
        """测试文件不存在时抛出异常"""
        with pytest.raises(FileNotFoundError, match="Parquet 文件不存在"):
            load_bars_from_parquet("/nonexistent/path/file.parquet", sample_instrument)

    def test_load_bars_from_parquet_with_columns(self, tmp_path, sample_instrument):
        """测试指定列加载"""
        parquet_path = tmp_path / "test.parquet"
        df = pd.DataFrame({
            "timestamp": pd.date_range("2023-01-01", periods=10),
            "open": [1.0] * 10,
            "high": [2.0] * 10,
            "low": [0.5] * 10,
            "close": [1.5] * 10,
            "volume": [100] * 10,
            "extra_col": [0] * 10,
        })
        df.to_parquet(parquet_path, index=False)

        bars = load_bars_from_parquet(
            parquet_path,
            sample_instrument,
            columns=["timestamp", "open", "high", "low", "close", "volume"],
        )
        assert bars is not None
        assert len(bars) == 10

    def test_load_bars_from_parquet_with_column_mapping(self, tmp_path, sample_instrument):
        """测试使用列名映射"""
        parquet_path = tmp_path / "test.parquet"
        df = pd.DataFrame({
            "ts": pd.date_range("2023-01-01", periods=10),
            "o": [1.0] * 10,
            "h": [2.0] * 10,
            "l": [0.5] * 10,
            "c": [1.5] * 10,
            "v": [100] * 10,
        })
        df.to_parquet(parquet_path, index=False)

        mapping = {"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"}
        bars = load_bars_from_parquet(
            parquet_path,
            sample_instrument,
            column_mapping=mapping,
            timestamp_column="ts",
        )
        assert bars is not None
        assert len(bars) == 10


# =============================================================================
# 错误处理测试
# =============================================================================

class TestErrorHandling:
    """测试错误处理"""

    @patch("backend.backtest.adapters.data_adapter.pd.read_csv")
    def test_load_bars_from_csv_pandas_error(self, mock_read_csv, sample_instrument):
        """测试 pandas 读取错误"""
        mock_read_csv.side_effect = Exception("Pandas error")

        with patch.object(Path, "exists", return_value=True):
            with pytest.raises(Exception, match="Pandas error"):
                load_bars_from_csv("fake.csv", sample_instrument)

    @patch("backend.backtest.adapters.data_adapter.pd.read_parquet")
    def test_load_bars_from_parquet_pandas_error(self, mock_read_parquet, sample_instrument):
        """测试 pandas parquet 读取错误"""
        mock_read_parquet.side_effect = Exception("Parquet error")

        with patch.object(Path, "exists", return_value=True):
            with pytest.raises(Exception, match="Parquet error"):
                load_bars_from_parquet("fake.parquet", sample_instrument)
