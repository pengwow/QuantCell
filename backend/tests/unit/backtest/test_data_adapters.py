"""多数据类型适配器单元测试。

覆盖 BaseDataAdapter、DataAdapterFactory、KlineAdapter、
TickAdapter、DerivAdapter、OrderBookAdapter。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from backtest.data_adapters.base_adapter import (
    AdapterResult,
    BaseDataAdapter,
    LoadConfig,
)


class ConcreteAdapter(BaseDataAdapter):
    """用于测试的具体适配器。"""

    _SUPPORTED_TYPES = {"test_type"}

    def load(self, config: LoadConfig) -> AdapterResult:
        df = pd.DataFrame({"close": [100.0, 101.0, 102.0]})
        return AdapterResult(data=df, metadata={"type": "test"})


class TestLoadConfig:
    def test_default_values(self):
        config = LoadConfig(symbol="BTCUSDT", data_type="kline")
        assert config.market == "spot"
        assert config.interval == "1h"
        assert config.start is None
        assert config.end is None

    def test_custom_values(self):
        config = LoadConfig(
            symbol="ETHUSDT",
            data_type="aggTrades",
            market="um",
            interval="5m",
            start="20250101",
            end="20251231",
        )
        assert config.symbol == "ETHUSDT"
        assert config.market == "um"
        assert config.interval == "5m"


class TestAdapterResult:
    def test_result_creation(self):
        df = pd.DataFrame({"close": [100.0]})
        result = AdapterResult(data=df)
        assert len(result.data) == 1
        assert result.features is None
        assert result.metadata == {}

    def test_result_with_features(self):
        df = pd.DataFrame({"close": [100.0]})
        features = pd.DataFrame({"funding_rate": [0.0001]})
        result = AdapterResult(
            data=df,
            features=features,
            metadata={"has_funding": True},
        )
        assert result.features is not None
        assert result.metadata["has_funding"] is True


class TestBaseDataAdapter:
    def test_supports_correct_type(self):
        adapter = ConcreteAdapter()
        assert adapter.supports("test_type") is True

    def test_supports_wrong_type(self):
        adapter = ConcreteAdapter()
        assert adapter.supports("invalid_type") is False

    def test_load_returns_dataframe(self):
        adapter = ConcreteAdapter()
        config = LoadConfig(symbol="BTCUSDT", data_type="test_type")
        result = adapter.load(config)
        assert isinstance(result, AdapterResult)
        assert len(result.data) == 3

    @patch("pathlib.Path.glob")
    def test_find_parquet_raises_when_not_found(self, mock_glob):
        mock_glob.return_value = []
        adapter = ConcreteAdapter(base_dir=Path("/nonexistent"))
        with pytest.raises(FileNotFoundError, match="未找到数据文件"):
            adapter._find_parquet("kline", "spot", "BTCUSDT")


class TestDataAdapterFactory:
    def test_create_kline_adapter(self):
        from backtest.data_adapters.factory import DataAdapterFactory
        from backtest.data_adapters.kline_adapter import KlineAdapter

        adapter = DataAdapterFactory.create("kline")
        assert isinstance(adapter, KlineAdapter)

    def test_create_tick_adapter(self):
        from backtest.data_adapters.factory import DataAdapterFactory
        from backtest.data_adapters.tick_adapter import TickAdapter

        adapter = DataAdapterFactory.create("aggTrades")
        assert isinstance(adapter, TickAdapter)

    def test_create_deriv_adapter(self):
        from backtest.data_adapters.factory import DataAdapterFactory
        from backtest.data_adapters.deriv_adapter import DerivAdapter

        adapter = DataAdapterFactory.create("fundingRate")
        assert isinstance(adapter, DerivAdapter)

    def test_create_orderbook_adapter(self):
        from backtest.data_adapters.factory import DataAdapterFactory
        from backtest.data_adapters.orderbook_adapter import OrderBookAdapter

        adapter = DataAdapterFactory.create("bookDepth")
        assert isinstance(adapter, OrderBookAdapter)

    def test_create_mark_price_kline(self):
        from backtest.data_adapters.factory import DataAdapterFactory
        from backtest.data_adapters.kline_adapter import KlineAdapter

        adapter = DataAdapterFactory.create("markPriceKlines")
        assert isinstance(adapter, KlineAdapter)

    def test_unsupported_type_raises(self):
        from backtest.data_adapters.factory import DataAdapterFactory

        with pytest.raises(ValueError, match="不支持的数据类型"):
            DataAdapterFactory.create("invalidType")

    def test_list_supported_types(self):
        from backtest.data_adapters.factory import DataAdapterFactory

        types = DataAdapterFactory.list_supported_types()
        assert "kline" in types
        assert "aggTrades" in types
        assert "fundingRate" in types
        assert len(types) == 10

    def test_get_adapter_class(self):
        from backtest.data_adapters.factory import DataAdapterFactory

        cls = DataAdapterFactory.get_adapter_class("kline")
        assert cls is not None
        assert DataAdapterFactory.get_adapter_class("invalidType") is None


class TestKlineAdapter:
    def test_supports_kline(self):
        from backtest.data_adapters.kline_adapter import KlineAdapter

        adapter = KlineAdapter()
        assert adapter.supports("kline") is True

    def test_supports_mark_price(self):
        from backtest.data_adapters.kline_adapter import KlineAdapter

        adapter = KlineAdapter()
        assert adapter.supports("markPriceKlines") is True

    def test_does_not_support_tick(self):
        from backtest.data_adapters.kline_adapter import KlineAdapter

        adapter = KlineAdapter()
        assert adapter.supports("aggTrades") is False

    @patch("backtest.data_adapters.kline_adapter.KlineAdapter._load_parquet")
    @patch("backtest.data_adapters.kline_adapter.KlineAdapter._find_parquet")
    def test_load_normalizes_columns(self, mock_find, mock_load):
        from backtest.data_adapters.kline_adapter import KlineAdapter

        mock_find.return_value = Path("/fake/path/data.parquet")
        mock_load.return_value = pd.DataFrame(
            {
                "open": [100.0, 101.0],
                "high": [105.0, 106.0],
                "low": [99.0, 100.0],
                "close": [103.0, 104.0],
                "volume": [1000.0, 2000.0],
            }
        )
        adapter = KlineAdapter()
        config = LoadConfig(symbol="BTCUSDT", data_type="kline", interval="1h")
        result = adapter.load(config)
        assert "Open" in result.data.columns
        assert "High" in result.data.columns
        assert "Close" in result.data.columns
        assert len(result.data) == 2


class TestTickAdapter:
    def test_supports_agg_trades(self):
        from backtest.data_adapters.tick_adapter import TickAdapter

        adapter = TickAdapter()
        assert adapter.supports("aggTrades") is True

    def test_supports_trades(self):
        from backtest.data_adapters.tick_adapter import TickAdapter

        adapter = TickAdapter()
        assert adapter.supports("trades") is True

    def test_does_not_support_kline(self):
        from backtest.data_adapters.tick_adapter import TickAdapter

        adapter = TickAdapter()
        assert adapter.supports("kline") is False

    @patch("backtest.data_adapters.tick_adapter.TickAdapter._load_parquet")
    @patch("backtest.data_adapters.tick_adapter.TickAdapter._find_parquet")
    def test_aggregate_to_ohlcv(self, mock_find, mock_load):
        from backtest.data_adapters.tick_adapter import TickAdapter

        mock_find.return_value = Path("/fake/path/data.parquet")
        timestamps = pd.date_range("2025-01-01", periods=100, freq="1s")
        mock_load.return_value = pd.DataFrame(
            {
                "timestamp": timestamps,
                "price": np.random.uniform(100, 110, 100),
                "quantity": np.random.uniform(0.1, 1.0, 100),
            }
        )
        mock_load.return_value["timestamp"] = (
            mock_load.return_value["timestamp"].astype("int64") // 1_000_000
        )

        adapter = TickAdapter()
        config = LoadConfig(
            symbol="BTCUSDT", data_type="aggTrades", interval="10s"
        )
        result = adapter.load(config)

        assert "Open" in result.data.columns
        assert "Close" in result.data.columns
        assert "Volume" in result.data.columns
        assert len(result.data) == 10  # 100 ticks / 10s = 10 bars

    def test_detect_column_raises_for_missing(self):
        from backtest.data_adapters.tick_adapter import TickAdapter

        adapter = TickAdapter()
        df = pd.DataFrame({"col1": [1], "col2": [2]})
        with pytest.raises(ValueError, match="未找到价格列"):
            adapter._detect_column(df, ["price", "p"], "价格")


class TestDerivAdapter:
    def test_supports_funding_rate(self):
        from backtest.data_adapters.deriv_adapter import DerivAdapter

        adapter = DerivAdapter()
        assert adapter.supports("fundingRate") is True

    def test_supports_open_interest(self):
        from backtest.data_adapters.deriv_adapter import DerivAdapter

        adapter = DerivAdapter()
        assert adapter.supports("openInterest") is True

    def test_does_not_support_kline(self):
        from backtest.data_adapters.deriv_adapter import DerivAdapter

        adapter = DerivAdapter()
        assert adapter.supports("kline") is False

    def test_process_funding_rate_without_mark_price_raises(self):
        from backtest.data_adapters.deriv_adapter import DerivAdapter

        adapter = DerivAdapter(base_dir=Path("/nonexistent"))
        config = LoadConfig(
            symbol="BTCUSDT", data_type="fundingRate", market="um", interval="8h"
        )
        with pytest.raises(ValueError, match="需要 markPriceKlines"):
            adapter._process_funding_rate(config)

    @patch("backtest.data_adapters.deriv_adapter.DerivAdapter._load_parquet")
    @patch("backtest.data_adapters.deriv_adapter.DerivAdapter._find_parquet")
    def test_process_funding_rate_with_mark_price(self, mock_find, mock_load):
        from backtest.data_adapters.deriv_adapter import DerivAdapter

        call_count = [0]

        def mock_load_side_effect(path):
            call_count[0] += 1
            if call_count[0] == 1:
                # 第一次调用: markPrice 数据（在 _try_load_mark_price 中）
                return pd.DataFrame(
                    {
                        "open": [100.0, 101.0, 102.0],
                        "high": [105.0, 106.0, 107.0],
                        "low": [99.0, 100.0, 101.0],
                        "close": [103.0, 104.0, 105.0],
                        "volume": [1000.0, 2000.0, 1500.0],
                        "timestamp": pd.date_range(
                            "2025-01-01", periods=3, freq="8h"
                        ).astype("int64")
                        // 1_000_000,
                    }
                )
            else:
                # 第二次调用: fundingRate 数据
                return pd.DataFrame(
                    {
                        "fundingRate": [0.0001, -0.0002, 0.00015],
                        "fundingTime": pd.date_range(
                            "2025-01-01", periods=3, freq="8h"
                        ).astype("int64")
                        // 1_000_000,
                    }
                )

        mock_load.side_effect = mock_load_side_effect
        # 顺序: 先 markPriceKlines, 再 fundingRate
        mock_find.side_effect = [
            Path("/fake/mark_price.parquet"),
            Path("/fake/funding_rate.parquet"),
        ]

        adapter = DerivAdapter()
        config = LoadConfig(
            symbol="BTCUSDT", data_type="fundingRate", market="um", interval="8h"
        )
        result = adapter.load(config)

        assert "feature_funding_rate" in result.data.columns
        assert len(result.data) == 3
        assert result.metadata["has_funding_feature"] is True


class TestOrderBookAdapter:
    def test_supports_book_ticker(self):
        from backtest.data_adapters.orderbook_adapter import OrderBookAdapter

        adapter = OrderBookAdapter()
        assert adapter.supports("bookTicker") is True

    def test_supports_book_depth(self):
        from backtest.data_adapters.orderbook_adapter import OrderBookAdapter

        adapter = OrderBookAdapter()
        assert adapter.supports("bookDepth") is True

    def test_does_not_support_kline(self):
        from backtest.data_adapters.orderbook_adapter import OrderBookAdapter

        adapter = OrderBookAdapter()
        assert adapter.supports("kline") is False

    @patch("backtest.data_adapters.orderbook_adapter.OrderBookAdapter._load_parquet")
    @patch("backtest.data_adapters.orderbook_adapter.OrderBookAdapter._find_parquet")
    def test_process_book_ticker(self, mock_find, mock_load):
        from backtest.data_adapters.orderbook_adapter import OrderBookAdapter

        mock_find.return_value = Path("/fake/path/bookTicker.parquet")
        timestamps = pd.date_range("2025-01-01", periods=60, freq="1s")
        mock_load.return_value = pd.DataFrame(
            {
                "timestamp": timestamps.astype("int64") // 1_000_000,
                "bidPrice": np.random.uniform(100, 101, 60),
                "askPrice": np.random.uniform(101, 102, 60),
                "bidQty": np.random.uniform(1, 10, 60),
                "askQty": np.random.uniform(1, 10, 60),
            }
        )

        adapter = OrderBookAdapter()
        config = LoadConfig(
            symbol="BTCUSDT", data_type="bookTicker", interval="10s"
        )
        result = adapter.load(config)

        assert "feature_mid_price" in result.data.columns
        assert "feature_spread" in result.data.columns
        assert len(result.data) == 6  # 60 ticks / 10s = 6 bars


class TestIntegration:
    """端到端集成测试。"""

    def test_full_factory_workflow(self):
        """测试工厂创建适配器的完整流程。"""
        from backtest.data_adapters.factory import DataAdapterFactory

        for data_type in DataAdapterFactory.list_supported_types():
            adapter = DataAdapterFactory.create(data_type)
            assert adapter is not None
            assert adapter.supports(data_type)

    def test_context_feature_injection(self):
        """测试 StrategyContext 特征注入。"""
        from strategy.base import StrategyContext

        ctx = StrategyContext(
            symbol="BTCUSDT",
            data_type="fundingRate",
            features={"funding_rate": 0.0001},
        )
        assert ctx.get_feature("funding_rate") == 0.0001
        assert ctx.has_feature("funding_rate") is True
        assert ctx.has_feature("nonexistent") is False
        assert ctx.get_feature("nonexistent", 0.5) == 0.5

    def test_data_type_validation(self):
        """测试数据类型验证。"""
        from backtest.data_adapters.factory import DataAdapterFactory

        with pytest.raises(ValueError):
            DataAdapterFactory.create("invalid_type_xyz")

        try:
            DataAdapterFactory.create("invalid_type_xyz")
        except ValueError as e:
            assert "支持的类型" in str(e) or "不支持" in str(e)

    def test_tick_column_detection(self):
        """测试 Tick 列检测。"""
        from backtest.data_adapters.tick_adapter import TickAdapter

        adapter = TickAdapter()
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2025-01-01", periods=10, freq="1s"),
                "price": [100 + i for i in range(10)],
                "quantity": [0.1] * 10,
            }
        )
        time_col = adapter._detect_column(df, ["timestamp", "T"], "时间")
        price_col = adapter._detect_column(df, ["price", "p"], "价格")
        qty_col = adapter._detect_column(df, ["quantity", "qty"], "数量")
        assert time_col == "timestamp"
        assert price_col == "price"
        assert qty_col == "quantity"
