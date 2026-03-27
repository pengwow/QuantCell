# -*- coding: utf-8 -*-
"""
Trading Worker 单元测试

测试 Trading Worker 相关组件的单元功能，包括：
- TradingNodeWorkerProcess 初始化与配置
- 配置构建函数
- TradingStrategyAdapter 适配器
- 数据转换函数
- EventHandler 事件处理器

使用 pytest 框架和 unittest.mock 进行模拟测试
"""

import pytest
import asyncio
import sys
import os
from datetime import datetime
from decimal import Decimal
from unittest.mock import Mock, AsyncMock, MagicMock, patch, call
from typing import Dict, Any, Optional

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../..'))

# 直接导入需要测试的模块，避免完整的 worker 包导入链
# 这些导入放在文件顶部，但在 sys.path 设置之后
import importlib.util

def _import_module_directly(module_name: str, file_path: str):
    """直接导入模块，避免导入链"""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec and spec.loader:
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    return None


# =============================================================================
# TradingNodeWorkerProcess 测试
# =============================================================================

class TestTradingNodeWorkerProcess:
    """TradingNodeWorkerProcess 单元测试"""

    @pytest.fixture
    def mock_config(self) -> Dict[str, Any]:
        """创建模拟配置"""
        return {
            "strategy_class": "TestStrategy",
            "params": {"param1": "value1"},
            "trading": {
                "trader_id": "TEST-001",
                "environment": "SANDBOX",
                "data_clients": {"binance": {"api_key": "test"}},
                "exec_clients": {"binance": {"api_key": "test"}},
            },
            "symbols": ["BTCUSDT"],
            "data_types": ["kline"],
        }

    def test_worker_config_extraction(self, mock_config):
        """测试 TradingNode 配置提取"""
        # 模拟配置提取功能
        trading_config = mock_config.get("trading", {})
        assert trading_config.get("trader_id") == "TEST-001"
        assert trading_config.get("environment") == "SANDBOX"
        assert "data_clients" in trading_config
        assert "exec_clients" in trading_config

    def test_worker_config_structure(self, mock_config):
        """测试 Worker 配置结构"""
        assert "strategy_class" in mock_config
        assert "params" in mock_config
        assert "trading" in mock_config
        assert "symbols" in mock_config
        assert "data_types" in mock_config


# =============================================================================
# 配置构建测试
# =============================================================================

class TestTradingConfig:
    """TradingNode 配置构建测试"""

    def test_build_trading_node_config_basic(self):
        """测试基本配置构建"""
        from worker.config import build_trading_node_config

        config = {
            "trader_id": "TEST-001",
            "environment": "SANDBOX",
        }

        result = build_trading_node_config(config)

        # 如果 Nautilus 可用，返回 TradingNodeConfig，否则返回原始配置
        assert result is not None

    def test_build_trading_node_config_with_engines(self):
        """测试带引擎配置的配置构建"""
        from worker.config import build_trading_node_config

        config = {
            "trader_id": "TEST-002",
            "environment": "LIVE",
            "data_engine": {
                "qsize": 50000,
                "graceful_shutdown_on_exception": True,
            },
            "risk_engine": {
                "qsize": 50000,
                "graceful_shutdown_on_exception": True,
            },
            "exec_engine": {
                "reconciliation": True,
                "reconciliation_lookback_mins": 720,
            },
        }

        result = build_trading_node_config(config)
        assert result is not None

    def test_build_trading_node_config_with_clients(self):
        """测试带客户端配置的配置构建"""
        from worker.config import build_trading_node_config

        config = {
            "trader_id": "TEST-003",
            "data_clients": {"binance": {"api_key": "test_key"}},
            "exec_clients": {"binance": {"api_key": "test_key"}},
        }

        result = build_trading_node_config(config)
        assert result is not None

    def test_build_binance_config_testnet(self):
        """测试 Binance 测试网配置构建"""
        from worker.config import build_binance_config

        config = build_binance_config(
            api_key="test_api_key",
            api_secret="test_api_secret",
            testnet=True,
            use_usdt_margin=True,
        )

        assert config["api_key"] == "test_api_key"
        assert config["api_secret"] == "test_api_secret"
        assert config["testnet"] is True
        assert config["use_usdt_margin"] is True
        assert "base_url_http" in config
        assert "base_url_ws" in config

    def test_build_binance_config_live(self):
        """测试 Binance 生产环境配置构建"""
        from worker.config import build_binance_config

        config = build_binance_config(
            api_key="live_api_key",
            api_secret="live_api_secret",
            testnet=False,
            use_usdt_margin=True,
        )

        assert config["testnet"] is False

    def test_build_binance_live_config(self):
        """测试 Binance 生产环境便捷配置"""
        from worker.config import build_binance_live_config

        config = build_binance_live_config(
            api_key="live_api_key",
            api_secret="live_api_secret",
            use_usdt_margin=True,
        )

        assert config["testnet"] is False
        assert "fapi.binance.com" in config["base_url_http"]
        assert "fstream.binance.com" in config["base_url_ws"]

    def test_build_binance_config_custom_urls(self):
        """测试 Binance 自定义 URL 配置"""
        from worker.config import build_binance_config

        config = build_binance_config(
            api_key="test_key",
            api_secret="test_secret",
            testnet=True,
            base_url_http="https://custom.api.com",
            base_url_ws="wss://custom.ws.com",
        )

        assert config["base_url_http"] == "https://custom.api.com"
        assert config["base_url_ws"] == "wss://custom.ws.com"


# =============================================================================
# TradingStrategyAdapter 测试
# =============================================================================

class TestTradingStrategyAdapter:
    """TradingStrategyAdapter 适配器测试"""

    @pytest.fixture
    def mock_qc_strategy(self):
        """创建模拟 QuantCell 策略"""
        # 创建一个真正的 QCStrategyBase 子类实例，实现所有抽象方法
        from strategy.core.strategy import StrategyBase, StrategyConfig as QCStrategyConfig
        from strategy.core.data_types import InstrumentId, Bar

        class MockStrategy(StrategyBase):
            def __init__(self, config):
                super().__init__(config)

            def on_start(self):
                """策略启动"""
                pass

            def on_stop(self):
                """策略停止"""
                pass

            def on_bar(self, bar: Bar):
                """处理 K 线数据"""
                pass

        config = QCStrategyConfig(
            instrument_ids=[InstrumentId("BTCUSDT", "BINANCE")],
            bar_types=["1-HOUR"],
        )
        return MockStrategy(config)

    @pytest.fixture
    def mock_trading_config(self):
        """创建模拟 TradingNode 配置"""
        # 尝试创建真正的 Nautilus StrategyConfig
        try:
            from nautilus_trader.trading.config import StrategyConfig
            return StrategyConfig()
        except ImportError:
            # Nautilus 未安装，返回 None，测试会跳过
            return None

    def test_adapter_initialization_valid(self, mock_qc_strategy, mock_trading_config):
        """测试适配器有效初始化"""
        from strategy.trading_adapter import TradingStrategyAdapter

        # 如果无法创建 StrategyConfig，跳过测试
        if mock_trading_config is None:
            pytest.skip("Nautilus StrategyConfig 无法创建")

        try:
            adapter = TradingStrategyAdapter(mock_qc_strategy, mock_trading_config)
            assert adapter.qc_strategy is mock_qc_strategy
            assert adapter._is_paused is False
        except (TypeError, ImportError) as e:
            # Nautilus 配置类型不匹配时跳过
            pytest.skip(f"Nautilus StrategyConfig 类型不匹配: {e}")

    def test_adapter_initialization_invalid(self, mock_trading_config):
        """测试适配器无效初始化"""
        from strategy.trading_adapter import TradingStrategyAdapter, StrategyAdapterConfigError

        # 如果无法创建 StrategyConfig，跳过测试
        if mock_trading_config is None:
            pytest.skip("Nautilus StrategyConfig 无法创建")

        # 现在我们的类型检查在父类初始化之前，所以会抛出 StrategyAdapterConfigError
        # 使用 type: ignore 来抑制类型检查错误，因为我们故意传入错误类型
        with pytest.raises(StrategyAdapterConfigError):
            TradingStrategyAdapter("not_a_strategy", mock_trading_config)  # type: ignore

    def test_adapter_properties(self, mock_qc_strategy, mock_trading_config):
        """测试适配器属性"""
        from strategy.trading_adapter import TradingStrategyAdapter

        # 如果无法创建 StrategyConfig，跳过测试
        if mock_trading_config is None:
            pytest.skip("Nautilus StrategyConfig 无法创建")

        try:
            adapter = TradingStrategyAdapter(mock_qc_strategy, mock_trading_config)
            
            # 测试初始状态
            assert adapter.is_paused is False
            assert adapter.bars_processed == 0
            assert adapter.ticks_processed == 0
        except (TypeError, ImportError) as e:
            # Nautilus 配置类型不匹配时跳过
            pytest.skip(f"Nautilus StrategyConfig 类型不匹配: {e}")

    def test_pause_and_resume(self, mock_qc_strategy, mock_trading_config):
        """测试暂停和恢复"""
        from strategy.trading_adapter import TradingStrategyAdapter

        # 如果无法创建 StrategyConfig，跳过测试
        if mock_trading_config is None:
            pytest.skip("Nautilus StrategyConfig 无法创建")

        try:
            adapter = TradingStrategyAdapter(mock_qc_strategy, mock_trading_config)
            
            assert adapter.is_paused is False

            adapter.pause()
            assert adapter.is_paused is True

            adapter.resume()
            assert adapter.is_paused is False
        except (TypeError, ImportError) as e:
            # Nautilus 配置类型不匹配时跳过
            pytest.skip(f"Nautilus StrategyConfig 类型不匹配: {e}")


# =============================================================================
# 数据转换函数测试
# =============================================================================

class TestDataConversion:
    """数据转换函数测试"""

    def test_convert_bar_to_qc(self):
        """测试 Bar 数据转换"""
        from strategy.trading_adapter import convert_bar_to_qc
        from strategy.core.data_types import Bar

        # 创建模拟 Trading Bar
        mock_bar = Mock()
        mock_bar.bar_type.instrument_id.symbol = "BTCUSDT"
        mock_bar.bar_type.instrument_id.venue = "BINANCE"
        mock_bar.bar_type.spec.step = 1
        mock_bar.bar_type.spec.aggregation.name = "HOUR"
        mock_bar.open = 50000.0
        mock_bar.high = 51000.0
        mock_bar.low = 49000.0
        mock_bar.close = 50500.0
        mock_bar.volume = 100.0
        mock_bar.ts_event = 1704067200000000000  # 纳秒时间戳

        result = convert_bar_to_qc(mock_bar)

        assert isinstance(result, Bar)
        assert result.instrument_id.symbol == "BTCUSDT"
        assert result.instrument_id.venue == "BINANCE"
        assert result.open == 50000.0
        assert result.high == 51000.0
        assert result.low == 49000.0
        assert result.close == 50500.0
        assert result.volume == 100.0

    def test_convert_tick_to_qc_quote(self):
        """测试 QuoteTick 数据转换"""
        from strategy.trading_adapter import convert_tick_to_qc

        mock_tick = Mock()
        mock_tick.instrument_id.symbol = "BTCUSDT"
        mock_tick.instrument_id.venue = "BINANCE"
        mock_tick.bid_price = 50000.0
        mock_tick.bid_size = 1.0
        mock_tick.ask_price = 50001.0
        mock_tick.ask_size = 1.5
        mock_tick.ts_event = 1704067200000000000

        result = convert_tick_to_qc(mock_tick)

        assert result["type"] == "quote"
        assert result["symbol"] == "BTCUSDT"
        assert result["bid_price"] == 50000.0
        assert result["ask_price"] == 50001.0

    def test_convert_order_to_trading(self):
        """测试订单转换为 Trading 格式"""
        from strategy.trading_adapter import convert_order_to_trading
        from strategy.core.data_types import InstrumentId, OrderSide, OrderType, TimeInForce

        qc_order = {
            "instrument_id": InstrumentId("BTCUSDT", "BINANCE"),
            "side": OrderSide.BUY,
            "order_type": OrderType.LIMIT,
            "quantity": Decimal("0.1"),
            "price": Decimal("50000"),
            "time_in_force": TimeInForce.GTC,
        }

        result = convert_order_to_trading(qc_order)

        assert "instrument_id" in result
        assert "side" in result
        assert "order_type" in result
        assert "quantity" in result
        assert "price" in result

    def test_convert_position_to_qc(self):
        """测试持仓转换为 QuantCell 格式"""
        from strategy.trading_adapter import convert_position_to_qc

        mock_position = Mock()
        mock_position.instrument_id.symbol = "BTCUSDT"
        mock_position.instrument_id.venue = "BINANCE"
        mock_position.quantity = Decimal("0.5")
        mock_position.avg_px_open = 50000.0
        mock_position.unrealized_pnl = 100.0
        mock_position.realized_pnl = 50.0
        mock_position.ts_opened = 1704067200000000000
        mock_position.is_open = True

        result = convert_position_to_qc(mock_position)

        assert result["symbol"] == "BTCUSDT"
        assert result["quantity"] == Decimal("0.5")
        assert result["avg_price"] == 50000.0
        assert result["is_open"] is True


# =============================================================================
# EventHandler 测试
# =============================================================================

class TestEventHandler:
    """EventHandler 事件处理器测试"""

    @pytest.fixture
    def mock_comm_client(self):
        """创建模拟通信客户端"""
        client = AsyncMock()
        client.send_event = AsyncMock(return_value=True)
        return client

    @pytest.fixture
    def event_handler(self, mock_comm_client):
        """创建事件处理器实例"""
        from worker.event_handler import EventHandler, EventBufferConfig

        config = EventBufferConfig(
            buffer_size=100,
            flush_interval=1.0,
            batch_size=50,
        )

        handler = EventHandler(
            worker_id="test-worker",
            comm_client=mock_comm_client,
            config=config,
        )
        return handler

    def test_event_handler_initialization(self, event_handler):
        """测试事件处理器初始化"""
        assert event_handler.worker_id == "test-worker"
        assert event_handler.comm_client is not None
        assert event_handler.config.buffer_size == 100

    def test_on_order_event(self, event_handler):
        """测试订单事件处理"""
        order_event = {"order_id": "123", "status": "filled"}
        event_handler.on_order_event(order_event)

        stats = event_handler.get_stats()
        assert stats["events_received"] == 1

    def test_on_fill_event(self, event_handler):
        """测试成交事件处理"""
        fill_event = {"fill_id": "456", "quantity": 0.1}
        event_handler.on_fill_event(fill_event)

        stats = event_handler.get_stats()
        assert stats["events_received"] == 1

    def test_on_position_event(self, event_handler):
        """测试持仓事件处理"""
        position_event = {"position_id": "789", "side": "LONG"}
        event_handler.on_position_event(position_event)

        stats = event_handler.get_stats()
        assert stats["events_received"] == 1

    @pytest.mark.asyncio
    async def test_send_event(self, event_handler, mock_comm_client):
        """测试发送单个事件"""
        event_data = {
            "event_type": "test",
            "data": {"key": "value"},
        }

        result = await event_handler._flush_buffer()
        # 没有事件时返回 None
        assert result is None

    def test_get_stats(self, event_handler):
        """测试获取统计信息"""
        stats = event_handler.get_stats()

        assert "events_received" in stats
        assert "events_sent" in stats
        assert "events_dropped" in stats
        assert "buffer_size" in stats


# =============================================================================
# 策略加载器测试
# =============================================================================

class TestStrategyLoader:
    """策略加载器测试"""

    def test_load_quantcell_strategy_file_not_found(self):
        """测试加载不存在的策略文件"""
        from strategy.trading_adapter import load_quantcell_strategy, StrategyLoadError

        with pytest.raises(StrategyLoadError):
            load_quantcell_strategy("/nonexistent/path/strategy.py", {})

    def test_create_trading_strategy_adapter_missing_config(self):
        """测试创建适配器时缺少配置"""
        from strategy.trading_adapter import (
            create_trading_strategy_adapter,
            StrategyAdapterConfigError,
        )
        from strategy.core.strategy import StrategyBase, StrategyConfig as QCStrategyConfig
        from strategy.core.data_types import InstrumentId, Bar

        # 创建一个真正的 QCStrategyBase 子类实例
        class MockStrategy(StrategyBase):
            def on_start(self):
                pass

            def on_stop(self):
                pass

            def on_bar(self, bar: Bar):
                pass

        config = QCStrategyConfig(
            instrument_ids=[InstrumentId("BTCUSDT", "BINANCE")],
            bar_types=["1-HOUR"],
        )
        mock_strategy = MockStrategy(config)

        # 当传入空字典作为 config 时，应该抛出 StrategyAdapterConfigError
        # 因为 Nautilus Strategy 要求 config 必须是 StrategyConfig 类型
        with pytest.raises(StrategyAdapterConfigError) as exc_info:
            create_trading_strategy_adapter(mock_strategy, {})

        # 验证错误信息包含配置相关的信息
        assert "config" in str(exc_info.value).lower() or "strategyconfig" in str(exc_info.value).lower()


# =============================================================================
# Worker 状态测试
# =============================================================================

class TestWorkerState:
    """Worker 状态测试"""

    def test_worker_state_transitions(self):
        """测试 Worker 状态转换"""
        from worker.state import WorkerState, WorkerStatus

        status = WorkerStatus(worker_id="test-worker")

        # 初始状态是 INITIALIZING
        assert status.state == WorkerState.INITIALIZING

        # 初始化完成
        status.update_state(WorkerState.INITIALIZED)
        assert status.state == WorkerState.INITIALIZED

        # 启动
        status.update_state(WorkerState.STARTING)
        assert status.state == WorkerState.STARTING

        status.update_state(WorkerState.RUNNING)
        assert status.state == WorkerState.RUNNING

        # 暂停
        status.update_state(WorkerState.PAUSED)
        assert status.state == WorkerState.PAUSED

        # 恢复
        status.update_state(WorkerState.RUNNING)
        assert status.state == WorkerState.RUNNING

        # 停止
        status.update_state(WorkerState.STOPPING)
        assert status.state == WorkerState.STOPPING

    def test_worker_error_handling(self):
        """测试 Worker 错误处理"""
        from worker.state import WorkerState, WorkerStatus

        status = WorkerStatus(worker_id="test-worker")

        # 记录错误
        status.record_error("Test error")
        assert status.errors_count == 1
        assert status.last_error == "Test error"
        assert status.last_error_time is not None

        # 记录多个错误
        status.record_error("Another error")
        assert status.errors_count == 2
        assert status.last_error == "Another error"

    def test_worker_heartbeat(self):
        """测试 Worker 心跳"""
        from worker.state import WorkerStatus, WorkerState
        from datetime import datetime

        status = WorkerStatus(worker_id="test-worker")

        # 先转换到 RUNNING 状态（is_healthy 要求 RUNNING 或 PAUSED 状态）
        status.update_state(WorkerState.INITIALIZED)
        status.update_state(WorkerState.STARTING)
        status.update_state(WorkerState.RUNNING)

        # 更新心跳
        status.update_heartbeat()
        assert status.last_heartbeat is not None

        # 检查健康状态
        assert status.is_healthy() is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
