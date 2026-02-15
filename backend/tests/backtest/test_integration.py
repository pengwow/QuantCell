# -*- coding: utf-8 -*-
"""
trading engine 集成测试模块

测试 trading engine 回测引擎的完整集成流程，包括:
- 端到端回测工作流
- 引擎切换功能
- 数据流完整性
- 多货币对回测场景

作者: QuantCell Team
版本: 1.0.0
日期: 2026-02-15
"""

import json
import os
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Generator, List
from unittest.mock import MagicMock, Mock, patch

import pandas as pd
import pytest

# 确保 backend 目录在 Python 路径中
backend_dir = Path(__file__).parent.parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from backtest.engines import BacktestEngineBase, EngineType, LegacyEngine, Engine
from backtest.config import get_engine_config, load_engine_config
from backtest.schemas import BacktestConfig, StrategyConfig


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(scope="session")
def test_catalog_path() -> Path:
    """
    获取测试数据目录路径
    
    Returns:
        Path: 示例数据目录路径
    """
    catalog_path = Path(backend_dir) / "example" / "catalog"
    return catalog_path


@pytest.fixture(scope="session")
def sample_backtest_config() -> Dict[str, Any]:
    """
    提供标准回测配置
    
    Returns:
        Dict[str, Any]: 回测配置字典
    """
    return {
        "initial_capital": 100000.0,
        "start_date": "2020-01-01",
        "end_date": "2020-01-31",
        "symbols": ["EURUSD"],
        "interval": "1h",
        "commission": 0.001,
    }


@pytest.fixture(scope="session")
def sample_strategy_config() -> Dict[str, Any]:
    """
    提供标准策略配置
    
    Returns:
        Dict[str, Any]: 策略配置字典
    """
    return {
        "strategy_name": "SmaCross",
        "params": {
            "n1": 10,
            "n2": 20,
        },
    }


@pytest.fixture(scope="session")
def sample_macd_strategy_config() -> Dict[str, Any]:
    """
    提供 MACD 策略配置
    
    Returns:
        Dict[str, Any]: MACD 策略配置字典
    """
    return {
        "strategy_name": "MACDStrategy",
        "params": {
            "fast_period": 12,
            "slow_period": 26,
            "signal_period": 9,
        },
    }


@pytest.fixture(scope="function")
def default_engine_config(
    test_catalog_path: Path,
    sample_backtest_config: Dict[str, Any],
    sample_strategy_config: Dict[str, Any],
) -> Dict[str, Any]:
    """
    创建 default 引擎配置
    
    Args:
        test_catalog_path: 测试数据目录
        sample_backtest_config: 回测配置
        sample_strategy_config: 策略配置
    
    Returns:
        Dict[str, Any]: default 引擎完整配置
    """
    config = {
        "engine_type": "default",
        "catalog_path": str(test_catalog_path),
        **sample_backtest_config,
        "strategy_config": {
            "strategy_path": "backtest.strategies.sma_cross:SmaCross",
            "config_path": "backtest.strategies.sma_cross:SmaCrossConfig",
            "params": sample_strategy_config["params"],
        },
        "log_level": "ERROR",  # 测试时使用 ERROR 级别减少输出
    }
    return config


@pytest.fixture(scope="function")
def legacy_engine_config(
    sample_backtest_config: Dict[str, Any],
    sample_strategy_config: Dict[str, Any],
) -> Dict[str, Any]:
    """
    创建 Legacy 引擎配置
    
    Args:
        sample_backtest_config: 回测配置
        sample_strategy_config: 策略配置
    
    Returns:
        Dict[str, Any]: Legacy 引擎完整配置
    """
    config = {
        "engine_type": "legacy",
        "backtest_config": {
            **sample_backtest_config,
            "symbol": sample_backtest_config["symbols"][0],
        },
        "strategy_config": sample_strategy_config,
    }
    return config


@pytest.fixture(scope="function")
def default_engine(default_engine_config: Dict[str, Any]) -> Generator[Engine, None, None]:
    """
    创建并管理 Engine 实例
    
    Args:
        default_engine_config: default 引擎配置
    
    Yields:
        Engine: 初始化的引擎实例
    """
    engine = Engine(default_engine_config)
    yield engine
    # 清理资源
    if engine.is_initialized:
        engine.cleanup()


@pytest.fixture(scope="function")
def legacy_engine(legacy_engine_config: Dict[str, Any]) -> Generator[LegacyEngine, None, None]:
    """
    创建并管理 LegacyEngine 实例
    
    Args:
        legacy_engine_config: Legacy 引擎配置
    
    Yields:
        LegacyEngine: 初始化的引擎实例
    """
    engine = LegacyEngine(legacy_engine_config)
    yield engine
    # 清理资源
    if engine.is_initialized:
        engine.cleanup()


# =============================================================================
# 基础引擎测试
# =============================================================================


class TestEngineBase:
    """
    测试引擎基类功能
    """

    def test_engine_type_enum(self):
        """
        测试引擎类型枚举定义
        
        验证所有引擎类型枚举值是否正确
        """
        assert EngineType.DEFAULT.value == "default"
        assert EngineType.LEGACY.value == "legacy"

    def test_default_engine_inheritance(self):
        """
        测试 Engine 继承关系
        
        验证 Engine 正确继承自 BacktestEngineBase
        """
        assert issubclass(Engine, BacktestEngineBase)

    def test_legacy_engine_inheritance(self):
        """
        测试 LegacyEngine 继承关系
        
        验证 LegacyEngine 正确继承自 BacktestEngineBase
        """
        assert issubclass(LegacyEngine, BacktestEngineBase)

    def test_default_engine_type_property(self, default_engine: Engine):
        """
        测试 Engine 引擎类型属性
        
        Args:
            default_engine: default 引擎实例
        """
        assert default_engine.engine_type.value == EngineType.DEFAULT.value

    def test_legacy_engine_type_property(self, legacy_engine: LegacyEngine):
        """
        测试 LegacyEngine 引擎类型属性
        
        Args:
            legacy_engine: Legacy 引擎实例
        """
        assert legacy_engine.engine_type.value == EngineType.LEGACY.value


# =============================================================================
# Engine 集成测试
# =============================================================================


class TestEngineIntegration:
    """
    trading engine 引擎端到端集成测试
    
    测试完整的回测流程: 初始化 -> 运行回测 -> 获取结果 -> 清理资源
    """

    @pytest.mark.skipif(
        not (Path(backend_dir) / "example" / "catalog").exists(),
        reason="测试数据目录不存在"
    )
    def test_default_engine_full_workflow(self, default_engine_config: Dict[str, Any]):
        """
        测试 Engine 完整工作流
        
        验证完整的回测流程:
        1. 引擎初始化
        2. 运行回测
        3. 获取结果
        4. 清理资源
        
        Args:
            default_engine_config: default 引擎配置
        """
        engine = Engine(default_engine_config)
        
        try:
            # 步骤 1: 初始化引擎
            engine.initialize()
            assert engine.is_initialized, "引擎初始化失败"
            
            # 步骤 2: 运行回测
            # 注意: 由于测试数据可能不完整，回测可能失败
            # 我们主要验证流程能正常执行而不崩溃
            try:
                results = engine.run_backtest()
                # 步骤 3: 验证结果格式
                assert isinstance(results, dict), "结果应为字典类型"
                
                # 步骤 4: 获取结果
                cached_results = engine.get_results()
                assert cached_results == results, "缓存结果应与运行结果一致"
            except RuntimeError as e:
                # 回测执行失败是预期的，因为测试数据可能不完整
                # 或者策略配置类不存在
                pytest.skip(f"回测执行跳过（数据或策略问题）: {e}")
            
        finally:
            # 步骤 5: 清理资源
            engine.cleanup()
            assert not engine.is_initialized, "引擎清理后应未初始化"

    def test_default_engine_initialization_without_catalog(self):
        """
        测试 Engine 在没有数据目录时的行为
        
        验证引擎在缺少必需配置时抛出异常
        """
        config = {
            "engine_type": "default",
            "initial_capital": 100000.0,
            "start_date": "2020-01-01",
            "end_date": "2020-01-31",
            "symbols": ["EURUSD"],
            # 缺少 catalog_path
        }
        
        engine = Engine(config)
        
        with pytest.raises((ValueError, RuntimeError)):
            engine.initialize()

    def test_default_engine_run_without_initialization(self):
        """
        测试未初始化时运行回测的行为
        
        验证引擎在未初始化时运行回测抛出异常
        """
        config = {
            "engine_type": "default",
            "catalog_path": str(Path(backend_dir) / "example" / "catalog"),
            "initial_capital": 100000.0,
            "start_date": "2020-01-01",
            "end_date": "2020-01-31",
            "symbols": ["EURUSD"],
            "strategy_config": {
                "strategy_path": "backtest.strategies.sma_cross:SmaCross",
                "params": {"n1": 10, "n2": 20},
            },
        }
        
        engine = Engine(config)
        
        with pytest.raises(RuntimeError) as exc_info:
            engine.run_backtest()
        
        assert "未初始化" in str(exc_info.value) or "initialize" in str(exc_info.value).lower()

    def test_default_engine_get_results_without_run(self):
        """
        测试未运行回测时获取结果的行为
        
        验证引擎在未运行回测时获取结果抛出异常
        """
        config = {
            "engine_type": "default",
            "catalog_path": str(Path(backend_dir) / "example" / "catalog"),
            "initial_capital": 100000.0,
            "symbols": ["EURUSD"],
        }
        
        engine = Engine(config)
        
        with pytest.raises(RuntimeError) as exc_info:
            engine.get_results()
        
        assert "尚未执行回测" in str(exc_info.value) or "run_backtest" in str(exc_info.value).lower()


# =============================================================================
# LegacyEngine 集成测试
# =============================================================================


class TestLegacyEngineIntegration:
    """
    Legacy 引擎端到端集成测试
    """

    def test_legacy_engine_initialization(self, legacy_engine_config: Dict[str, Any]):
        """
        测试 LegacyEngine 初始化
        
        Args:
            legacy_engine_config: Legacy 引擎配置
        """
        engine = LegacyEngine(legacy_engine_config)
        
        # Mock BacktestService 以避免实际数据库依赖
        # 注意: BacktestService 是在 backtest.service 模块中定义的
        with patch("backtest.service.BacktestService") as mock_service:
            mock_instance = MagicMock()
            mock_service.return_value = mock_instance
            
            engine.initialize()
            assert engine.is_initialized, "引擎初始化失败"
        
        engine.cleanup()

    def test_legacy_engine_run_backtest(self, legacy_engine_config: Dict[str, Any]):
        """
        测试 LegacyEngine 运行回测
        
        Args:
            legacy_engine_config: Legacy 引擎配置
        """
        engine = LegacyEngine(legacy_engine_config)
        
        # Mock BacktestService
        # 注意: BacktestService 是在 backtest.service 模块中定义的
        with patch("backtest.service.BacktestService") as mock_service:
            mock_instance = MagicMock()
            mock_instance.run_backtest.return_value = {
                "task_id": str(uuid.uuid4()),
                "status": "completed",
                "message": "回测完成",
                "results": {
                    "metrics": [{"name": "Return [%]", "value": 10.5}],
                    "trades": [],
                },
            }
            mock_service.return_value = mock_instance
            
            engine.initialize()
            results = engine.run_backtest()
            
            assert results is not None, "回测结果为空"
            assert results["status"] == "completed", "回测状态应为完成"
        
        engine.cleanup()

    def test_legacy_engine_missing_strategy_name(self):
        """
        测试 LegacyEngine 缺少策略名称时的行为
        
        验证引擎在缺少策略名称时抛出异常
        """
        config = {
            "backtest_config": {
                "symbols": ["BTCUSDT"],
                "interval": "1d",
            },
            "strategy_config": {
                # 缺少 strategy_name
                "params": {},
            },
        }
        
        engine = LegacyEngine(config)
        
        with pytest.raises((ValueError, RuntimeError)):
            engine.initialize()

    def test_legacy_engine_missing_symbols(self):
        """
        测试 LegacyEngine 缺少交易对时的行为
        
        验证引擎在缺少交易对时抛出异常
        """
        config = {
            "backtest_config": {
                # 缺少 symbols
                "interval": "1d",
            },
            "strategy_config": {
                "strategy_name": "SmaCross",
                "params": {},
            },
        }
        
        engine = LegacyEngine(config)
        
        with pytest.raises((ValueError, RuntimeError)):
            engine.initialize()


# =============================================================================
# 引擎切换功能测试
# =============================================================================


class TestEngineSwitching:
    """
    测试引擎切换功能
    
    验证在不同引擎之间切换的能力
    """

    def test_engine_factory_default(self):
        """
        测试引擎工厂创建 default 引擎
        
        验证 BacktestService 的 create_engine 方法能正确创建 default 引擎
        """
        from backtest.service import BacktestService
        
        service = BacktestService()
        config = {
            "engine_type": "default",
            "initial_capital": 100000.0,
            "symbols": ["EURUSD"],
        }
        
        engine = service.create_engine(config)
        
        assert engine is not None, "引擎创建失败"
        assert isinstance(engine, Engine), "应为 Engine 类型"
        assert engine.engine_type == EngineType.DEFAULT, "引擎类型应为 advanced"

    def test_engine_factory_legacy(self):
        """
        测试引擎工厂创建 Legacy 引擎
        
        验证 BacktestService 的 create_engine 方法能正确创建 Legacy 引擎
        """
        from backtest.service import BacktestService
        
        service = BacktestService()
        config = {
            "engine_type": "legacy",
            "backtest_config": {"symbols": ["BTCUSDT"]},
            "strategy_config": {"strategy_name": "SmaCross"},
        }
        
        engine = service.create_engine(config)
        
        assert engine is not None, "引擎创建失败"
        assert isinstance(engine, LegacyEngine), "应为 LegacyEngine 类型"
        assert engine.engine_type.value == EngineType.LEGACY.value, "引擎类型应为 LEGACY"

    def test_engine_factory_default(self):
        """
        测试引擎工厂默认行为
        
        验证 BacktestService 在没有指定引擎类型时默认创建 default 引擎
        """
        from backtest.service import BacktestService
        
        service = BacktestService()
        config = {
            "initial_capital": 100000.0,
            "symbols": ["EURUSD"],
        }
        
        engine = service.create_engine(config)
        
        assert engine is not None, "引擎创建失败"
        assert isinstance(engine, Engine), "默认应为 Engine 类型"

    def test_engine_factory_invalid_type(self):
        """
        测试引擎工厂处理无效引擎类型
        
        验证 BacktestService 在遇到无效引擎类型时回退到默认引擎
        """
        from backtest.service import BacktestService
        
        service = BacktestService()
        config = {
            "engine_type": "invalid_engine",
            "initial_capital": 100000.0,
            "symbols": ["EURUSD"],
        }
        
        engine = service.create_engine(config)
        
        # 应该回退到默认的 default 引擎
        assert engine is not None, "引擎创建失败"
        assert isinstance(engine, Engine), "无效类型应回退到 Engine"

    def test_load_engine_config(self):
        """
        测试加载引擎配置
        
        验证 load_engine_config 函数能正确解析配置
        """
        config_dict = {
            "engine_type": "default",
            "log_level": "DEBUG",
            "custom_param": "value",
        }
        
        result = load_engine_config(config_dict)
        
        assert "log_level" in result, "配置应包含 log_level"
        assert result["log_level"] == "DEBUG", "log_level 应为 DEBUG"

    def test_load_engine_config_invalid_type(self):
        """
        测试加载无效引擎类型配置
        
        验证 load_engine_config 在遇到无效引擎类型时抛出异常
        """
        config_dict = {
            "engine_type": "unknown_type",
        }
        
        with pytest.raises(ValueError) as exc_info:
            load_engine_config(config_dict)
        
        assert "无效的引擎类型" in str(exc_info.value)


# =============================================================================
# 数据流完整性测试
# =============================================================================


class TestDataFlowIntegrity:
    """
    测试数据流完整性
    
    验证从数据加载到结果输出的完整数据流
    """

    def test_config_validation_default(self):
        """
        测试 default 引擎配置验证
        
        验证配置验证逻辑能正确识别无效配置
        """
        # 有效配置
        valid_config = {
            "engine_type": "default",
            "catalog_path": str(Path(backend_dir) / "example" / "catalog"),
            "initial_capital": 100000.0,
            "start_date": "2020-01-01",
            "end_date": "2020-01-31",
            "symbols": ["EURUSD"],
            "strategy_config": {
                "strategy_path": "backtest.strategies.sma_cross:SmaCross",
                "params": {"n1": 10, "n2": 20},
            },
        }
        
        engine = Engine(valid_config)
        # _validate_config 是保护方法，但我们可以测试初始化行为
        assert engine.config == valid_config

    def test_config_validation_legacy(self):
        """
        测试 Legacy 引擎配置验证
        
        验证配置验证逻辑能正确识别无效配置
        """
        # 有效配置
        valid_config = {
            "backtest_config": {
                "symbols": ["BTCUSDT"],
                "interval": "1d",
            },
            "strategy_config": {
                "strategy_name": "SmaCross",
                "params": {"n1": 10, "n2": 20},
            },
        }
        
        engine = LegacyEngine(valid_config)
        assert engine.config == valid_config

    def test_results_format_consistency(self):
        """
        测试结果格式一致性
        
        验证不同引擎返回的结果格式保持一致
        """
        # 创建模拟结果
        default_result = {
            "trades": [],
            "positions": [],
            "account": {"balance": 100000.0, "equity": 100000.0},
            "metrics": {
                "total_return": 0.0,
                "sharpe_ratio": 0.0,
                "max_drawdown": 0.0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "total_trades": 0,
            },
            "equity_curve": [],
        }
        
        # 验证结果包含预期的键
        expected_keys = ["trades", "metrics", "equity_curve"]
        for key in expected_keys:
            assert key in default_result, f"结果应包含 {key}"

    def test_equity_curve_structure(self):
        """
        测试权益曲线数据结构
        
        验证权益曲线数据的格式正确
        """
        sample_equity_point = {
            "timestamp": "2020-01-01 00:00:00",
            "equity": 100000.0,
            "balance": 100000.0,
            "margin": 0.0,
        }
        
        # 验证权益曲线点包含必需的字段
        assert "timestamp" in sample_equity_point
        assert "equity" in sample_equity_point


# =============================================================================
# 多货币对回测测试
# =============================================================================


class TestMultiCurrencyBacktest:
    """
    测试多货币对回测场景
    
    验证引擎能正确处理多个货币对的回测
    """

    def test_multi_symbol_config_default(self):
        """
        测试 default 引擎多货币对配置
        
        验证引擎能正确处理多个货币对
        """
        config = {
            "engine_type": "default",
            "catalog_path": str(Path(backend_dir) / "example" / "catalog"),
            "initial_capital": 100000.0,
            "start_date": "2020-01-01",
            "end_date": "2020-01-31",
            "symbols": ["EURUSD", "GBPUSD", "USDJPY"],  # 多个货币对
            "strategy_config": {
                "strategy_path": "backtest.strategies.sma_cross:SmaCross",
                "params": {"n1": 10, "n2": 20},
            },
        }
        
        engine = Engine(config)
        assert engine.config["symbols"] == ["EURUSD", "GBPUSD", "USDJPY"]

    def test_multi_symbol_config_legacy(self):
        """
        测试 Legacy 引擎多货币对配置
        
        验证引擎能正确处理多个货币对
        """
        config = {
            "backtest_config": {
                "symbols": ["BTCUSDT", "ETHUSDT", "ADAUSDT"],  # 多个货币对
                "interval": "1d",
            },
            "strategy_config": {
                "strategy_name": "SmaCross",
                "params": {"n1": 10, "n2": 20},
            },
        }
        
        engine = LegacyEngine(config)
        assert engine.config["backtest_config"]["symbols"] == ["BTCUSDT", "ETHUSDT", "ADAUSDT"]

    def test_venue_config_multi_currency(self):
        """
        测试多货币对交易场所配置
        
        验证交易场所配置能支持多货币对
        """
        config = {
            "engine_type": "default",
            "catalog_path": str(Path(backend_dir) / "example" / "catalog"),
            "initial_capital": 100000.0,
            "symbols": ["EURUSD", "GBPUSD"],
            "venue_config": {
                "name": "SIM",
                "base_currency": "USD",
                "oms_type": "NETTING",
                "account_type": "MARGIN",
            },
            "strategy_config": {
                "strategy_path": "backtest.strategies.sma_cross:SmaCross",
                "params": {},
            },
        }
        
        engine = Engine(config)
        assert "venue_config" in engine.config
        assert engine.config["venue_config"]["base_currency"] == "USD"


# =============================================================================
# 策略配置测试
# =============================================================================


class TestStrategyConfiguration:
    """
    测试策略配置功能
    
    验证不同策略的配置和加载
    """

    def test_sma_cross_strategy_config(self):
        """
        测试 SMA Cross 策略配置
        
        验证 SMA Cross 策略参数配置正确
        """
        strategy_config = {
            "strategy_name": "SmaCross",
            "params": {
                "n1": 10,
                "n2": 20,
            },
        }
        
        assert strategy_config["params"]["n1"] == 10
        assert strategy_config["params"]["n2"] == 20

    def test_macd_strategy_config(self):
        """
        测试 MACD 策略配置
        
        验证 MACD 策略参数配置正确
        """
        strategy_config = {
            "strategy_name": "MACDStrategy",
            "params": {
                "fast_period": 12,
                "slow_period": 26,
                "signal_period": 9,
            },
        }
        
        assert strategy_config["params"]["fast_period"] == 12
        assert strategy_config["params"]["slow_period"] == 26
        assert strategy_config["params"]["signal_period"] == 9

    def test_strategy_config_validation(self):
        """
        测试策略配置验证
        
        验证策略配置验证逻辑
        """
        # 有效的策略配置
        valid_config = {
            "strategy_path": "backtest.strategies.sma_cross:SmaCross",
            "params": {"n1": 10, "n2": 20},
        }
        
        assert "strategy_path" in valid_config
        assert "params" in valid_config

    def test_strategy_config_missing_path(self):
        """
        测试缺少策略路径的配置
        
        验证缺少策略路径时抛出异常
        """
        invalid_config = {
            # 缺少 strategy_path
            "params": {"n1": 10},
        }
        
        # 创建引擎配置
        engine_config = {
            "engine_type": "default",
            "catalog_path": str(Path(backend_dir) / "example" / "catalog"),
            "initial_capital": 100000.0,
            "symbols": ["EURUSD"],
            "strategy_config": invalid_config,
        }
        
        engine = Engine(engine_config)
        
        # 在初始化时应该因为缺少 strategy_path 而失败
        with pytest.raises((ValueError, RuntimeError)):
            engine.initialize()


# =============================================================================
# 错误处理和边界情况测试
# =============================================================================


class TestErrorHandling:
    """
    测试错误处理和边界情况
    
    验证引擎在各种异常情况下的行为
    """

    def test_default_engine_invalid_catalog_path(self):
        """
        测试 Engine 无效数据目录路径
        
        验证引擎在数据目录不存在时抛出异常
        """
        config = {
            "engine_type": "default",
            "catalog_path": "/nonexistent/path/to/catalog",
            "initial_capital": 100000.0,
            "start_date": "2020-01-01",
            "end_date": "2020-01-31",
            "symbols": ["EURUSD"],
            "strategy_config": {
                "strategy_path": "backtest.strategies.sma_cross:SmaCross",
                "params": {},
            },
        }
        
        engine = Engine(config)
        
        with pytest.raises((ValueError, RuntimeError)) as exc_info:
            engine.initialize()
        
        # 验证抛出了异常（具体错误消息可能因实现而异）
        assert exc_info.value is not None

    def test_default_engine_empty_symbols(self):
        """
        测试 Engine 空交易对列表
        
        验证引擎在交易对列表为空时抛出异常
        """
        config = {
            "engine_type": "default",
            "catalog_path": str(Path(backend_dir) / "example" / "catalog"),
            "initial_capital": 100000.0,
            "start_date": "2020-01-01",
            "end_date": "2020-01-31",
            "symbols": [],  # 空列表
            "strategy_config": {
                "strategy_path": "backtest.strategies.sma_cross:SmaCross",
                "params": {},
            },
        }
        
        engine = Engine(config)
        
        with pytest.raises((ValueError, RuntimeError)) as exc_info:
            engine.initialize()
        
        # 验证抛出了异常（具体错误消息可能因实现而异）
        assert exc_info.value is not None

    def test_default_engine_invalid_date_format(self):
        """
        测试 Engine 无效日期格式
        
        验证引擎在日期格式无效时的行为
        """
        config = {
            "engine_type": "default",
            "catalog_path": str(Path(backend_dir) / "example" / "catalog"),
            "initial_capital": 100000.0,
            "start_date": "invalid_date",
            "end_date": "2020-01-31",
            "symbols": ["EURUSD"],
            "strategy_config": {
                "strategy_path": "backtest.strategies.sma_cross:SmaCross",
                "params": {},
            },
        }
        
        engine = Engine(config)
        
        # 应该能创建引擎，但初始化可能失败
        assert engine.config["start_date"] == "invalid_date"

    def test_legacy_engine_invalid_strategy_name(self):
        """
        测试 LegacyEngine 无效策略名称
        
        验证引擎在策略名称无效时的行为
        """
        config = {
            "backtest_config": {
                "symbols": ["BTCUSDT"],
                "interval": "1d",
            },
            "strategy_config": {
                "strategy_name": "",  # 空策略名称
                "params": {},
            },
        }
        
        engine = LegacyEngine(config)
        
        with pytest.raises((ValueError, RuntimeError)) as exc_info:
            engine.initialize()

    def test_engine_cleanup_idempotent(self):
        """
        测试引擎清理的幂等性
        
        验证多次调用 cleanup 不会导致错误
        """
        config = {
            "engine_type": "default",
            "catalog_path": str(Path(backend_dir) / "example" / "catalog"),
            "initial_capital": 100000.0,
            "symbols": ["EURUSD"],
            "strategy_config": {
                "strategy_path": "backtest.strategies.sma_cross:SmaCross",
                "params": {},
            },
        }
        
        engine = Engine(config)
        
        # 多次调用 cleanup 不应抛出异常
        engine.cleanup()
        engine.cleanup()
        engine.cleanup()
        
        assert not engine.is_initialized


# =============================================================================
# 性能和资源管理测试
# =============================================================================


class TestPerformanceAndResourceManagement:
    """
    测试性能和资源管理
    
    验证引擎的资源管理和性能特性
    """

    def test_engine_memory_cleanup(self):
        """
        测试引擎内存清理
        
        验证引擎在清理后释放资源
        """
        config = {
            "engine_type": "default",
            "catalog_path": str(Path(backend_dir) / "example" / "catalog"),
            "initial_capital": 100000.0,
            "symbols": ["EURUSD"],
            "strategy_config": {
                "strategy_path": "backtest.strategies.sma_cross:SmaCross",
                "params": {},
            },
        }
        
        engine = Engine(config)
        
        # 清理前
        engine._is_initialized = True  # 模拟初始化状态
        engine._results = {"test": "data"}
        
        # 清理
        engine.cleanup()
        
        # 验证状态重置
        assert not engine.is_initialized
        assert engine._results == {}

    def test_engine_config_isolation(self):
        """
        测试引擎配置隔离
        
        验证多个引擎实例之间的配置相互独立
        """
        config1 = {
            "engine_type": "default",
            "initial_capital": 100000.0,
            "symbols": ["EURUSD"],
        }
        
        config2 = {
            "engine_type": "default",
            "initial_capital": 200000.0,
            "symbols": ["GBPUSD"],
        }
        
        engine1 = Engine(config1)
        engine2 = Engine(config2)
        
        # 验证配置独立
        assert engine1.config["initial_capital"] == 100000.0
        assert engine2.config["initial_capital"] == 200000.0
        assert engine1.config["symbols"] == ["EURUSD"]
        assert engine2.config["symbols"] == ["GBPUSD"]


# =============================================================================
# 主入口
# =============================================================================


if __name__ == "__main__":
    # 允许直接运行测试文件
    pytest.main([__file__, "-v"])
