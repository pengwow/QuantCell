# -*- coding: utf-8 -*-
"""
回测引擎单元测试

测试 BacktestEngineBase 抽象接口、Engine、LegacyEngine 和引擎工厂方法。
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
from typing import Dict, Any

import pandas as pd
import numpy as np

from backtest.engines.base import BacktestEngineBase, EngineType as BaseEngineType
from backtest.engines.engine import Engine
from backtest.engines.legacy_engine import LegacyEngine
from backtest.config.settings import EngineType


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def base_engine_config():
    """基础引擎配置"""
    return {
        "initial_capital": 100000.0,
        "start_date": "2023-01-01",
        "end_date": "2023-12-31",
        "symbols": ["BTCUSDT"],
    }


@pytest.fixture
def engine_config(tmp_path):
    """高级引擎配置"""
    # 创建临时目录作为 catalog_path
    catalog_path = tmp_path / "catalog"
    catalog_path.mkdir()

    return {
        "initial_capital": 100000.0,
        "start_date": "2023-01-01",
        "end_date": "2023-12-31",
        "symbols": ["BTCUSDT"],
        "catalog_path": str(catalog_path),
        "strategy_config": {
            "strategy_path": "test_strategy:TestStrategy",
            "params": {"fast_period": 10, "slow_period": 20},
        },
        "venue_config": {
            "name": "SIM",
            "base_currency": "USDT",
        },
        "log_level": "INFO",
    }


@pytest.fixture
def legacy_engine_config():
    """Legacy 引擎配置"""
    return {
        "backtest_config": {
            "symbols": ["BTCUSDT"],
            "interval": "1h",
            "start_time": "2023-01-01",
            "end_time": "2023-12-31",
            "initial_cash": 100000.0,
        },
        "strategy_config": {
            "strategy_name": "TestStrategy",
            "params": {"fast_period": 10, "slow_period": 20},
        },
    }


@pytest.fixture
def mock_backtest_node():
    """模拟 BacktestNode"""
    node = Mock()
    node.run.return_value = [Mock()]
    node.get_engine.return_value = Mock()
    return node


@pytest.fixture
def mock_parquet_catalog():
    """模拟 ParquetDataCatalog"""
    catalog = Mock()
    return catalog


# =============================================================================
# BacktestEngineBase 抽象接口测试
# =============================================================================

class TestBacktestEngineBase:
    """测试 BacktestEngineBase 抽象基类"""

    def test_abstract_class_cannot_be_instantiated(self):
        """测试抽象类不能直接实例化"""
        with pytest.raises(TypeError):
            BacktestEngineBase()  # type: ignore

    def test_abstract_methods_must_be_implemented(self):
        """测试子类必须实现抽象方法"""
        class IncompleteEngine(BacktestEngineBase):
            @property
            def engine_type(self):
                return EngineType.DEFAULT

        with pytest.raises(TypeError):
            IncompleteEngine()  # type: ignore

    def test_concrete_engine_can_be_instantiated(self, base_engine_config):
        """测试具体引擎子类可以实例化"""
        class ConcreteEngine(BacktestEngineBase):
            @property
            def engine_type(self):
                return EngineType.DEFAULT

            def initialize(self):
                self._is_initialized = True

            def run_backtest(self):
                return {"result": "success"}

            def get_results(self):
                return self._results

            def cleanup(self):
                self._reset_state()

        engine = ConcreteEngine(base_engine_config)
        assert engine.config == base_engine_config
        assert not engine.is_initialized

    def test_config_property(self, base_engine_config):
        """测试配置属性"""
        class ConcreteEngine(BacktestEngineBase):
            @property
            def engine_type(self):
                return EngineType.DEFAULT

            def initialize(self):
                pass

            def run_backtest(self):
                return {}

            def get_results(self):
                return {}

            def cleanup(self):
                pass

        engine = ConcreteEngine(base_engine_config)

        # 测试 getter
        assert engine.config == base_engine_config

        # 测试 setter
        new_config = {"initial_capital": 200000.0}
        engine.config = new_config
        assert engine.config == new_config

    def test_validate_config_success(self, base_engine_config):
        """测试配置验证成功"""
        class ConcreteEngine(BacktestEngineBase):
            @property
            def engine_type(self):
                return EngineType.DEFAULT

            def initialize(self):
                pass

            def run_backtest(self):
                return {}

            def get_results(self):
                return {}

            def cleanup(self):
                pass

        engine = ConcreteEngine(base_engine_config)
        assert engine._validate_config() is True

    def test_validate_config_missing_required_keys(self):
        """测试配置验证失败 - 缺少必需参数"""
        class ConcreteEngine(BacktestEngineBase):
            @property
            def engine_type(self):
                return EngineType.DEFAULT

            def initialize(self):
                pass

            def run_backtest(self):
                return {}

            def get_results(self):
                return {}

            def cleanup(self):
                pass

        incomplete_config = {"initial_capital": 100000.0}  # 缺少 start_date, end_date
        engine = ConcreteEngine(incomplete_config)
        assert engine._validate_config() is False

    def test_reset_state(self, base_engine_config):
        """测试重置状态方法"""
        class ConcreteEngine(BacktestEngineBase):
            @property
            def engine_type(self):
                return EngineType.DEFAULT

            def initialize(self):
                pass

            def run_backtest(self):
                return {}

            def get_results(self):
                return {}

            def cleanup(self):
                pass

        engine = ConcreteEngine(base_engine_config)
        engine._is_initialized = True
        engine._results = {"test": "data"}

        engine._reset_state()

        assert not engine.is_initialized
        assert engine._results == {}


# =============================================================================
# Engine 测试
# =============================================================================

class TestEngine:
    """测试 Engine"""

    def test_initialization(self, engine_config):
        """测试 Engine 初始化"""
        engine = Engine(engine_config)

        assert engine.engine_type == EngineType.DEFAULT
        assert engine.config == engine_config
        assert not engine.is_initialized
        assert engine._node is None
        assert engine._catalog is None

    def test_engine_type_property(self, engine_config):
        """测试引擎类型属性"""
        engine = Engine(engine_config)
        assert engine.engine_type == EngineType.DEFAULT

    @patch("backtest.engines.engine.ParquetDataCatalog")
    @patch("backtest.engines.engine.BacktestNode")
    @patch("backtest.engines.engine.BacktestVenueConfig")
    @patch("backtest.engines.engine.BacktestDataConfig")
    @patch("backtest.engines.engine.BacktestEngineConfig")
    @patch("backtest.engines.engine.BacktestRunConfig")
    def test_initialize_success(
        self,
        mock_run_config_cls,
        mock_engine_config_cls,
        mock_data_config_cls,
        mock_venue_config_cls,
        mock_node_cls,
        mock_catalog_cls,
        engine_config,
    ):
        """测试初始化成功"""
        # 设置 mock
        mock_catalog = Mock()
        mock_catalog_cls.return_value = mock_catalog

        mock_venue_config = Mock()
        mock_venue_config.name = "SIM"
        mock_venue_config_cls.return_value = mock_venue_config

        mock_data_config = Mock()
        mock_data_config_cls.return_value = mock_data_config

        mock_engine_config = Mock()
        mock_engine_config_cls.return_value = mock_engine_config

        mock_run_config = Mock()
        mock_run_config.id = "test-run-id"
        mock_run_config_cls.return_value = mock_run_config

        mock_node = Mock()
        mock_node_cls.return_value = mock_node

        engine = Engine(engine_config)
        engine.initialize()

        assert engine.is_initialized
        assert engine._node is not None
        mock_catalog_cls.assert_called_once_with(engine_config["catalog_path"])
        mock_node_cls.assert_called_once_with(configs=[mock_run_config])

    def test_initialize_without_catalog_path(self, engine_config):
        """测试初始化失败 - 缺少 catalog_path"""
        del engine_config["catalog_path"]
        engine = Engine(engine_config)

        with pytest.raises(RuntimeError, match="引擎初始化失败"):
            engine.initialize()

    def test_initialize_without_strategy_config(self, engine_config):
        """测试初始化失败 - 缺少 strategy_config"""
        del engine_config["strategy_config"]
        engine = Engine(engine_config)

        with pytest.raises(RuntimeError, match="引擎初始化失败"):
            engine.initialize()

    def test_initialize_without_symbols(self, engine_config):
        """测试初始化失败 - 缺少 symbols"""
        del engine_config["symbols"]
        engine = Engine(engine_config)

        with pytest.raises(RuntimeError, match="引擎初始化失败"):
            engine.initialize()

    @patch("backtest.engines.engine.ParquetDataCatalog")
    def test_setup_catalog_path_not_exists(self, mock_catalog_cls, engine_config, tmp_path):
        """测试设置数据目录 - 路径不存在"""
        non_existent_path = tmp_path / "non_existent"
        engine_config["catalog_path"] = str(non_existent_path)
        engine = Engine(engine_config)

        with pytest.raises(ValueError, match="数据目录不存在"):
            engine._setup_catalog()

    @patch("backtest.engines.engine.ParquetDataCatalog")
    def test_setup_catalog_success(self, mock_catalog_cls, engine_config):
        """测试设置数据目录成功"""
        mock_catalog = Mock()
        mock_catalog_cls.return_value = mock_catalog

        engine = Engine(engine_config)
        engine._setup_catalog()

        assert engine._catalog is not None
        mock_catalog_cls.assert_called_once_with(engine_config["catalog_path"])

    def test_setup_venue_config_default(self, engine_config):
        """测试设置交易场所配置 - 使用默认值"""
        engine = Engine(engine_config)
        engine._setup_venue_config()

        assert engine._venue_config is not None

    def test_setup_venue_config_custom(self, engine_config):
        """测试设置交易场所配置 - 使用自定义值"""
        engine_config["venue_config"] = {
            "name": "BINANCE",
            "oms_type": "HEDGING",
            "account_type": "CASH",
            "base_currency": "BTC",
        }
        engine = Engine(engine_config)
        engine._setup_venue_config()

        assert engine._venue_config is not None

    def test_setup_data_config(self, engine_config):
        """测试设置数据配置"""
        engine = Engine(engine_config)
        engine._setup_data_config()

        assert engine._data_config is not None

    def test_build_strategy_configs(self, engine_config):
        """测试构建策略配置"""
        engine = Engine(engine_config)
        strategy_configs = engine._build_strategy_configs(
            engine_config["strategy_config"]
        )

        assert len(strategy_configs) == 1

    def test_build_strategy_configs_without_strategy_path(self, engine_config):
        """测试构建策略配置 - 缺少 strategy_path"""
        engine = Engine(engine_config)
        invalid_config = {"params": {}}

        with pytest.raises(ValueError, match="策略配置缺少必需参数"):
            engine._build_strategy_configs(invalid_config)

    def test_run_backtest_not_initialized(self, engine_config):
        """测试运行回测 - 未初始化"""
        engine = Engine(engine_config)

        with pytest.raises(RuntimeError, match="引擎未初始化"):
            engine.run_backtest()

    @patch("backtest.engines.engine.ParquetDataCatalog")
    @patch("backtest.engines.engine.BacktestNode")
    @patch("backtest.engines.engine.BacktestVenueConfig")
    @patch("backtest.engines.engine.BacktestDataConfig")
    @patch("backtest.engines.engine.BacktestEngineConfig")
    @patch("backtest.engines.engine.BacktestRunConfig")
    def test_run_backtest_success(
        self,
        mock_run_config_cls,
        mock_engine_config_cls,
        mock_data_config_cls,
        mock_venue_config_cls,
        mock_node_cls,
        mock_catalog_cls,
        engine_config,
    ):
        """测试运行回测成功"""
        # 设置 mocks
        mock_catalog = Mock()
        mock_catalog_cls.return_value = mock_catalog

        mock_venue_config = Mock()
        mock_venue_config.name = "SIM"
        mock_venue_config_cls.return_value = mock_venue_config

        mock_data_config = Mock()
        mock_data_config_cls.return_value = mock_data_config

        mock_engine_config = Mock()
        mock_engine_config_cls.return_value = mock_engine_config

        mock_run_config = Mock()
        mock_run_config.id = "test-run-id"
        mock_run_config_cls.return_value = mock_run_config

        # 模拟回测结果
        mock_engine_instance = Mock()
        mock_orders_df = pd.DataFrame({
            "order_id": ["order1", "order2"],
            "instrument_id": ["BTCUSDT.SIM", "BTCUSDT.SIM"],
            "side": ["BUY", "SELL"],
            "quantity": [1.0, 1.0],
            "price": [50000.0, 55000.0],
            "timestamp": pd.to_datetime(["2023-01-01", "2023-01-02"]),
        })
        mock_positions_df = pd.DataFrame({
            "position_id": ["pos1"],
            "instrument_id": ["BTCUSDT.SIM"],
            "side": ["LONG"],
            "quantity": [1.0],
            "avg_px_open": [50000.0],
            "avg_px_close": [55000.0],
            "realized_pnl": ["5000 USD"],
        })
        mock_account_df = pd.DataFrame({
            "balance": [100000.0, 105000.0],
            "margin": [0.0, 0.0],
            "equity": [100000.0, 105000.0],
            "timestamp": pd.to_datetime(["2023-01-01", "2023-01-02"]),
        })

        mock_engine_instance.trader.generate_order_fills_report.return_value = mock_orders_df
        mock_engine_instance.trader.generate_positions_report.return_value = mock_positions_df
        mock_engine_instance.trader.generate_account_report.return_value = mock_account_df

        mock_node = Mock()
        mock_node.run.return_value = [Mock()]
        mock_node.get_engine.return_value = mock_engine_instance
        mock_node_cls.return_value = mock_node

        engine = Engine(engine_config)
        engine.initialize()
        results = engine.run_backtest()

        assert "trades" in results
        assert "positions" in results
        assert "account" in results
        assert "metrics" in results
        assert "equity_curve" in results

    def test_get_results_not_run(self, engine_config):
        """测试获取结果 - 未运行回测"""
        engine = Engine(engine_config)

        with pytest.raises(RuntimeError, match="尚未执行回测"):
            engine.get_results()

    def test_cleanup(self, engine_config):
        """测试清理资源"""
        engine = Engine(engine_config)
        engine._is_initialized = True
        engine._results = {"test": "data"}

        engine.cleanup()

        assert not engine.is_initialized
        assert engine._results == {}
        assert engine._node is None
        assert engine._catalog is None

    def test_get_node(self, engine_config):
        """测试获取 BacktestNode"""
        engine = Engine(engine_config)
        assert engine.get_node() is None

    def test_get_engine_instance(self, engine_config):
        """测试获取引擎实例"""
        engine = Engine(engine_config)
        assert engine.get_engine_instance() is None

    def test_convert_orders_to_trades_empty(self, engine_config):
        """测试转换订单到交易 - 空数据"""
        engine = Engine(engine_config)
        result = engine._convert_orders_to_trades(None)
        assert result == []

        result = engine._convert_orders_to_trades(pd.DataFrame())
        assert result == []

    def test_convert_positions_empty(self, engine_config):
        """测试转换持仓 - 空数据"""
        engine = Engine(engine_config)
        result = engine._convert_positions(None)
        assert result == []

        result = engine._convert_positions(pd.DataFrame())
        assert result == []

    def test_convert_account_empty(self, engine_config):
        """测试转换账户 - 空数据"""
        engine = Engine(engine_config)
        result = engine._convert_account(None)
        assert result == {}

        result = engine._convert_account(pd.DataFrame())
        assert result == {}

    def test_calculate_metrics_empty(self, engine_config):
        """测试计算指标 - 空数据"""
        engine = Engine(engine_config)
        result = engine._calculate_metrics(None, None)

        assert result["total_return"] == 0.0
        assert result["sharpe_ratio"] == 0.0
        assert result["max_drawdown"] == 0.0
        assert result["win_rate"] == 0.0
        assert result["profit_factor"] == 0.0
        assert result["total_trades"] == 0

    def test_build_equity_curve_empty(self, engine_config):
        """测试构建权益曲线 - 空数据"""
        engine = Engine(engine_config)
        result = engine._build_equity_curve(None)
        assert result == []

        result = engine._build_equity_curve(pd.DataFrame())
        assert result == []


# =============================================================================
# LegacyEngine 测试
# =============================================================================

class TestLegacyEngine:
    """测试 LegacyEngine"""

    def test_initialization(self, legacy_engine_config):
        """测试 LegacyEngine 初始化"""
        engine = LegacyEngine(legacy_engine_config)

        assert engine.engine_type.value == EngineType.LEGACY.value
        assert engine.config == legacy_engine_config
        assert not engine.is_initialized
        assert engine._service is None

    def test_engine_type_property(self, legacy_engine_config):
        """测试引擎类型属性"""
        engine = LegacyEngine(legacy_engine_config)
        assert engine.engine_type.value == EngineType.LEGACY.value

    def test_validate_config_success(self, legacy_engine_config):
        """测试配置验证成功"""
        engine = LegacyEngine(legacy_engine_config)
        assert engine._validate_config() is True

    def test_validate_config_missing_symbols(self, legacy_engine_config):
        """测试配置验证失败 - 缺少 symbols"""
        del legacy_engine_config["backtest_config"]["symbols"]
        engine = LegacyEngine(legacy_engine_config)
        assert engine._validate_config() is False

    def test_validate_config_with_symbol_instead_of_symbols(self, legacy_engine_config):
        """测试配置验证 - 使用 symbol 替代 symbols"""
        del legacy_engine_config["backtest_config"]["symbols"]
        legacy_engine_config["backtest_config"]["symbol"] = "BTCUSDT"
        engine = LegacyEngine(legacy_engine_config)
        assert engine._validate_config() is True

    def test_validate_config_missing_strategy_name(self, legacy_engine_config):
        """测试配置验证失败 - 缺少 strategy_name"""
        del legacy_engine_config["strategy_config"]["strategy_name"]
        engine = LegacyEngine(legacy_engine_config)
        assert engine._validate_config() is False

    @patch("backtest.service.BacktestService")
    def test_initialize_success(self, mock_service_cls, legacy_engine_config):
        """测试初始化成功"""
        mock_service = Mock()
        mock_service_cls.return_value = mock_service

        engine = LegacyEngine(legacy_engine_config)
        engine.initialize()

        assert engine.is_initialized
        assert engine._service is not None
        mock_service_cls.assert_called_once()

    def test_initialize_config_validation_failure(self, legacy_engine_config):
        """测试初始化失败 - 配置验证失败"""
        del legacy_engine_config["backtest_config"]["symbols"]
        engine = LegacyEngine(legacy_engine_config)

        with pytest.raises(RuntimeError, match="配置验证失败"):
            engine.initialize()

    def test_initialize_missing_strategy_name(self, legacy_engine_config):
        """测试初始化失败 - 缺少策略名称"""
        del legacy_engine_config["strategy_config"]["strategy_name"]
        engine = LegacyEngine(legacy_engine_config)

        with pytest.raises(RuntimeError, match="配置验证失败"):
            engine.initialize()

    @patch("backtest.service.BacktestService")
    def test_run_backtest_success(self, mock_service_cls, legacy_engine_config):
        """测试运行回测成功"""
        mock_result = {
            "task_id": "test-task-123",
            "status": "success",
            "successful_currencies": ["BTCUSDT"],
            "failed_currencies": [],
            "results": {"BTCUSDT": {"total_return": 10.5}},
        }
        mock_service = Mock()
        mock_service.run_backtest.return_value = mock_result
        mock_service_cls.return_value = mock_service

        engine = LegacyEngine(legacy_engine_config)
        engine.initialize()
        result = engine.run_backtest()

        assert result["task_id"] == "test-task-123"
        assert result["status"] == "success"
        mock_service.run_backtest.assert_called_once()

    def test_run_backtest_not_initialized(self, legacy_engine_config):
        """测试运行回测 - 未初始化"""
        engine = LegacyEngine(legacy_engine_config)

        with pytest.raises(RuntimeError, match="引擎未初始化"):
            engine.run_backtest()

    @patch("backtest.service.BacktestService")
    def test_get_results_success(self, mock_service_cls, legacy_engine_config):
        """测试获取结果成功"""
        mock_result = {
            "task_id": "test-task-123",
            "status": "success",
            "results": {"BTCUSDT": {"total_return": 10.5}},
        }
        mock_service = Mock()
        mock_service.run_backtest.return_value = mock_result
        mock_service_cls.return_value = mock_service

        engine = LegacyEngine(legacy_engine_config)
        engine.initialize()
        engine.run_backtest()
        result = engine.get_results()

        assert result["task_id"] == "test-task-123"

    def test_get_results_not_run(self, legacy_engine_config):
        """测试获取结果 - 未运行回测"""
        engine = LegacyEngine(legacy_engine_config)

        with pytest.raises(RuntimeError, match="尚未执行回测"):
            engine.get_results()

    @patch("backtest.service.BacktestService")
    def test_cleanup(self, mock_service_cls, legacy_engine_config):
        """测试清理资源"""
        mock_service = Mock()
        mock_service_cls.return_value = mock_service

        engine = LegacyEngine(legacy_engine_config)
        engine.initialize()
        engine.cleanup()

        assert not engine.is_initialized
        assert engine._service is None
        assert engine._last_result is None

    def test_set_strategy_config(self, legacy_engine_config):
        """测试设置策略配置"""
        engine = LegacyEngine(legacy_engine_config)
        new_config = {"strategy_name": "NewStrategy", "params": {"n": 10}}
        engine.set_strategy_config(new_config)

        assert engine._strategy_config == new_config

    def test_set_backtest_config(self, legacy_engine_config):
        """测试设置回测配置"""
        engine = LegacyEngine(legacy_engine_config)
        new_config = {"symbols": ["ETHUSDT"], "interval": "4h"}
        engine.set_backtest_config(new_config)

        assert engine._backtest_config == new_config

    @patch("backtest.service.BacktestService")
    def test_analyze_result(self, mock_service_cls, legacy_engine_config):
        """测试分析回测结果"""
        mock_analysis = {"metrics": {"total_return": 15.0}}
        mock_service = Mock()
        mock_service.analyze_backtest.return_value = mock_analysis
        mock_service_cls.return_value = mock_service

        engine = LegacyEngine(legacy_engine_config)
        result = engine.analyze_result("test-backtest-id")

        assert result == mock_analysis
        mock_service.analyze_backtest.assert_called_once_with("test-backtest-id")

    @patch("backtest.service.BacktestService")
    def test_stop_backtest(self, mock_service_cls, legacy_engine_config):
        """测试终止回测"""
        mock_stop_result = {"status": "stopped"}
        mock_service = Mock()
        mock_service.stop_backtest.return_value = mock_stop_result
        mock_service_cls.return_value = mock_service

        engine = LegacyEngine(legacy_engine_config)
        result = engine.stop_backtest("test-task-id")

        assert result == mock_stop_result
        mock_service.stop_backtest.assert_called_once_with("test-task-id")


# =============================================================================
# 引擎工厂方法测试
# =============================================================================

class TestEngineFactory:
    """测试引擎工厂方法"""

    def test_create_default_engine(self, engine_config):
        """测试创建高级引擎"""
        from backtest.engines import Engine, LegacyEngine

        engine = Engine(engine_config)
        assert isinstance(engine, Engine)
        assert engine.engine_type == EngineType.DEFAULT

    def test_create_legacy_engine(self, legacy_engine_config):
        """测试创建 Legacy 引擎"""
        from backtest.engines import LegacyEngine

        engine = LegacyEngine(legacy_engine_config)
        assert isinstance(engine, LegacyEngine)
        assert engine.engine_type.value == EngineType.LEGACY.value

    def test_engine_type_enum_values(self):
        """测试引擎类型枚举值"""
        assert EngineType.DEFAULT.value == "default"
        assert EngineType.LEGACY.value == "legacy"
        assert BaseEngineType.EVENT_DRIVEN.value == "event_driven"
        assert BaseEngineType.VECTORIZED.value == "vectorized"
        assert BaseEngineType.CONCURRENT.value == "concurrent"
        assert BaseEngineType.ASYNC_EVENT.value == "async_event"

    def test_engine_inheritance(self, engine_config, legacy_engine_config):
        """测试引擎继承关系"""
        default_engine = Engine(engine_config)
        legacy_engine = LegacyEngine(legacy_engine_config)

        assert isinstance(default_engine, BacktestEngineBase)
        assert isinstance(legacy_engine, BacktestEngineBase)
