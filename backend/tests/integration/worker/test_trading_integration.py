# -*- coding: utf-8 -*-
"""
Trading Worker 集成测试

测试 Trading Worker 的完整集成流程，包括：
- Worker 启动/停止流程
- 策略加载和执行
- 事件同步机制
- 错误恢复
- TradingNodeWorkerManager 管理器

使用 pytest-asyncio 支持异步测试，使用 unittest.mock 进行模拟
"""

import pytest
import asyncio
import time
import tempfile
import os
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, MagicMock, patch, call
from typing import Dict, Any, Optional, List
import sys

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../..'))


# =============================================================================
# 集成测试基类
# =============================================================================

class TestTradingIntegrationBase:
    """交易集成测试基类"""

    @pytest.fixture(autouse=True)
    async def setup_teardown(self):
        """测试前后设置和清理"""
        # 测试前设置
        self.test_start_time = time.time()
        yield
        # 测试后清理
        await asyncio.sleep(0.1)  # 确保所有异步任务完成


# =============================================================================
# Worker 启动/停止流程测试
# =============================================================================

class TestWorkerLifecycle(TestTradingIntegrationBase):
    """Worker 生命周期集成测试"""

    @pytest.fixture
    def mock_trading_node(self):
        """创建模拟 TradingNode"""
        node = AsyncMock()
        node.start = AsyncMock()
        node.stop = AsyncMock()
        node.is_running = True
        node.strategies = []
        node.add_strategy = Mock()
        node.cancel_all_orders = AsyncMock()
        return node

    @pytest.fixture
    def sample_strategy_file(self):
        """创建示例策略文件"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('''
from trading_engine.trading.strategy import Strategy
from trading_engine.config import StrategyConfig

class TestStrategy(Strategy):
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
    
    def on_start(self):
        pass
    
    def on_stop(self):
        pass
    
    def on_bar(self, bar):
        pass
''')
            temp_path = f.name
        yield temp_path
        # 清理
        if os.path.exists(temp_path):
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_worker_full_lifecycle(self, mock_trading_node, sample_strategy_file):
        """测试 Worker 完整生命周期"""
        from worker.worker_process import TradingNodeWorkerProcess

        config = {
            "strategy_class": "TestStrategy",
            "params": {},
            "trading": {
                "trader_id": "TEST-001",
                "environment": "SANDBOX",
            },
        }

        with patch('worker.worker_process.TradingNode', return_value=mock_trading_node):
            with patch('worker.worker_process.build_trading_config', return_value={}):
                # 创建 Worker
                worker = TradingNodeWorkerProcess(
                    worker_id="test-lifecycle",
                    strategy_path=sample_strategy_file,
                    config=config,
                )

                # 验证初始状态
                assert worker.worker_id == "test-lifecycle"
                assert worker.trading_node is None

                # 初始化 TradingNode
                node = await worker._init_trading_node()
                assert node is mock_trading_node

                # 启动 Worker
                await worker._handle_start()
                mock_trading_node.start.assert_called_once()
                assert worker.status.state.name == "RUNNING"

                # 暂停 Worker
                await worker._handle_pause()
                assert worker.status.state.name == "PAUSED"

                # 恢复 Worker
                await worker._handle_resume()
                assert worker.status.state.name == "RUNNING"

                # 停止 Worker
                await worker._handle_stop()
                mock_trading_node.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_worker_restart_recovery(self, mock_trading_node, sample_strategy_file):
        """测试 Worker 重启恢复"""
        from worker.worker_process import TradingNodeWorkerProcess

        config = {
            "strategy_class": "TestStrategy",
            "params": {},
            "trading": {
                "trader_id": "TEST-RESTART",
                "environment": "SANDBOX",
            },
        }

        with patch('worker.worker_process.TradingNode', return_value=mock_trading_node):
            with patch('worker.worker_process.build_trading_config', return_value={}):
                # 第一次启动
                worker1 = TradingNodeWorkerProcess(
                    worker_id="test-restart",
                    strategy_path=sample_strategy_file,
                    config=config,
                )

                await worker1._init_trading_node()
                await worker1._handle_start()
                assert worker1.status.state.name == "RUNNING"

                # 模拟崩溃后重启
                await worker1._handle_stop()

                # 创建新 Worker 实例（模拟重启）
                worker2 = TradingNodeWorkerProcess(
                    worker_id="test-restart",
                    strategy_path=sample_strategy_file,
                    config=config,
                )

                await worker2._init_trading_node()
                await worker2._handle_start()
                assert worker2.status.state.name == "RUNNING"

                # 验证两次启动都成功
                assert mock_trading_node.start.call_count == 2


# =============================================================================
# 策略加载和执行测试
# =============================================================================

class TestStrategyExecution(TestTradingIntegrationBase):
    """策略执行集成测试"""

    @pytest.fixture
    def sample_strategy_content(self):
        """示例策略代码"""
        return '''
from trading_engine.trading.strategy import Strategy
from trading_engine.config import StrategyConfig
from trading_engine.model.data import Bar

class SampleStrategy(Strategy):
    """示例策略"""
    
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.bar_count = 0
    
    def on_start(self):
        self.log.info("策略启动")
    
    def on_stop(self):
        self.log.info("策略停止")
    
    def on_bar(self, bar: Bar):
        self.bar_count += 1
        self.log.info(f"收到K线: {bar}")
'''

    @pytest.fixture
    def strategy_file(self, sample_strategy_content):
        """创建策略文件"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(sample_strategy_content)
            temp_path = f.name
        yield temp_path
        if os.path.exists(temp_path):
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_strategy_load_and_execute(self, strategy_file):
        """测试策略加载和执行"""
        from worker.worker_process import TradingNodeWorkerProcess
        from trading_engine.model.data import Bar

        mock_node = AsyncMock()
        mock_node.start = AsyncMock()
        mock_node.stop = AsyncMock()
        mock_node.add_strategy = Mock()

        config = {
            "strategy_class": "SampleStrategy",
            "params": {},
            "trading": {
                "trader_id": "TEST-STRATEGY",
                "environment": "SANDBOX",
            },
        }

        with patch('worker.worker_process.TradingNode', return_value=mock_node):
            with patch('worker.worker_process.build_trading_config', return_value={}):
                worker = TradingNodeWorkerProcess(
                    worker_id="test-strategy",
                    strategy_path=strategy_file,
                    config=config,
                )

                # 初始化并启动
                await worker._init_trading_node()
                await worker._load_strategy()
                await worker._handle_start()

                # 验证策略已加载
                assert worker.trading_strategy is not None
                assert worker.status.strategy_name == "SampleStrategy"


# =============================================================================
# 事件同步机制测试
# =============================================================================

class TestEventSynchronization(TestTradingIntegrationBase):
    """事件同步集成测试"""

    @pytest.fixture
    def mock_comm_client(self):
        """创建模拟通信客户端"""
        client = AsyncMock()
        client.send_status = AsyncMock(return_value=True)
        client.connect = AsyncMock(return_value=True)
        client.disconnect = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_event_buffer_and_flush(self, mock_comm_client):
        """测试事件缓冲和刷新"""
        from worker.event_handler import EventHandler, EventBufferConfig

        config = EventBufferConfig(
            buffer_size=100,
            flush_interval=0.1,  # 短间隔用于测试
            max_batch_size=10,
        )

        with patch('worker.event_handler.Actor.__init__', return_value=None):
            handler = EventHandler(
                worker_id="test-events",
                comm_client=mock_comm_client,
                buffer_config=config,
            )

            # 添加事件到缓冲
            for i in range(5):
                handler._buffer_event("test", {"index": i})

            assert len(handler._event_buffer) == 5

            # 手动刷新
            await handler._flush_buffer()

            # 验证缓冲已清空
            assert len(handler._event_buffer) == 0

    @pytest.mark.asyncio
    async def test_batch_event_sync(self, mock_comm_client):
        """测试批量事件同步"""
        from worker.event_handler import EventHandler, EventBufferConfig

        config = EventBufferConfig(max_batch_size=3)

        with patch('worker.event_handler.Actor.__init__', return_value=None):
            handler = EventHandler(
                worker_id="test-batch",
                comm_client=mock_comm_client,
                buffer_config=config,
            )

            events = [
                {"type": "fill", "data": {"order_id": f"order-{i}"}}
                for i in range(10)
            ]

            result = await handler.batch_send_events(events)

            assert result is True
            # 验证通信客户端被调用
            assert mock_comm_client.send_status.called

    @pytest.mark.asyncio
    async def test_fill_event_conversion_and_sync(self, mock_comm_client):
        """测试成交事件转换和同步"""
        from worker.event_handler import (
            EventHandler, EventBufferConfig, convert_fill_to_qc
        )
        from trading_engine.execution.messages import OrderFilled

        config = EventBufferConfig()

        with patch('worker.event_handler.Actor.__init__', return_value=None):
            handler = EventHandler(
                worker_id="test-fill",
                comm_client=mock_comm_client,
                buffer_config=config,
            )

            # 创建模拟成交事件
            mock_fill = Mock(spec=OrderFilled)
            mock_fill.id = "fill-001"
            mock_fill.timestamp_ns = 1704067200000000000
            mock_fill.client_order_id = "order-001"
            mock_fill.trade_id = "trade-001"
            mock_fill.instrument_id = "BTCUSDT.BINANCE"
            mock_fill.venue = "BINANCE"
            mock_fill.order_side = "BUY"
            mock_fill.order_type = "LIMIT"
            mock_fill.last_qty = 0.1
            mock_fill.last_px = 50000.0
            mock_fill.commission = 0.001
            mock_fill.commission_currency = "BTC"
            mock_fill.liquidity_side = "MAKER"
            mock_fill.position_id = "pos-001"
            mock_fill.strategy_id = "strategy-001"

            # 转换并发送
            qc_event = convert_fill_to_qc(mock_fill)
            result = await handler.send_event("fill", qc_event)

            assert result is True
            mock_comm_client.send_status.assert_called_once()


# =============================================================================
# 错误恢复测试
# =============================================================================

class TestErrorRecovery(TestTradingIntegrationBase):
    """错误恢复集成测试"""

    @pytest.mark.asyncio
    async def test_worker_error_handling(self):
        """测试 Worker 错误处理"""
        from worker.worker_process import TradingNodeWorkerProcess
        from worker.state import WorkerState

        config = {
            "strategy_class": "NonExistentStrategy",
            "params": {},
            "trading": {},
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('# 空策略文件')
            temp_path = f.name

        try:
            worker = TradingNodeWorkerProcess(
                worker_id="test-error",
                strategy_path=temp_path,
                config=config,
            )

            # 尝试加载不存在的策略类
            with pytest.raises(Exception):
                await worker._load_strategy()

            # 验证错误状态
            assert worker.status.errors_count > 0

        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_trading_node_init_failure_recovery(self):
        """测试 TradingNode 初始化失败恢复"""
        from worker.worker_process import TradingNodeWorkerProcess

        config = {
            "trading": {
                "trader_id": "TEST-ERROR",
            },
        }

        with patch('worker.worker_process.build_trading_config', side_effect=Exception("Config error")):
            worker = TradingNodeWorkerProcess(
                worker_id="test-node-error",
                strategy_path="/tmp/test.py",
                config=config,
            )

            # 初始化应该返回 None 而不是抛出异常
            result = await worker._init_trading_node()
            assert result is None

            # 验证错误被记录
            assert len(worker.status.error_history) > 0

    @pytest.mark.asyncio
    async def test_strategy_method_error_handling(self):
        """测试策略方法错误处理"""
        from worker.worker_process import TradingNodeWorkerProcess

        worker = TradingNodeWorkerProcess(
            worker_id="test-method-error",
            strategy_path="/tmp/test.py",
            config={},
        )

        # 创建会抛出异常的策略方法
        mock_strategy = Mock()
        mock_strategy.error_method = Mock(side_effect=Exception("Method error"))
        worker.trading_strategy = mock_strategy

        # 调用应该捕获异常而不传播
        result = await worker._call_strategy_method("error_method")

        # 验证错误被记录但方法返回 None
        assert result is None
        assert worker.status.errors_count > 0


# =============================================================================
# TradingNodeWorkerManager 测试
# =============================================================================

class TestTradingNodeWorkerManager(TestTradingIntegrationBase):
    """TradingNodeWorkerManager 集成测试"""

    @pytest.fixture
    def manager_config(self):
        """管理器配置"""
        return {
            "max_workers": 5,
            "comm_host": "127.0.0.1",
            "data_port": 5555,
            "control_port": 5556,
            "status_port": 5557,
            "enable_monitoring": True,
        }

    @pytest.mark.asyncio
    async def test_manager_initialization(self, manager_config):
        """测试管理器初始化"""
        from worker.manager import TradingNodeWorkerManager

        with patch('worker.manager.WorkerManager.start', new_callable=AsyncMock, return_value=True):
            manager = TradingNodeWorkerManager(**manager_config)

            assert manager.max_workers == 5
            assert manager.comm_host == "127.0.0.1"
            assert manager.enable_monitoring is True
            assert manager.monitor is not None

    @pytest.mark.asyncio
    async def test_start_and_stop_trading_worker(self, manager_config):
        """测试启动和停止 Trading Worker"""
        from worker.manager import TradingNodeWorkerManager

        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('''
from trading_engine.trading.strategy import Strategy
class TestStrategy(Strategy):
    pass
''')
            strategy_path = f.name

        try:
            with patch('worker.manager.WorkerManager.start', new_callable=AsyncMock, return_value=True):
                with patch('worker.manager.WorkerManager.stop', new_callable=AsyncMock, return_value=True):
                    with patch('worker.worker_process.TradingNode'):
                        with patch('worker.worker_process.build_trading_config', return_value={}):
                            manager = TradingNodeWorkerManager(**manager_config)

                            # 启动 Worker
                            worker_id = await manager.start_trading_worker(
                                strategy_path=strategy_path,
                                config={"strategy_class": "TestStrategy"},
                            )

                            assert worker_id is not None
                            assert worker_id in manager._workers

                            # 停止 Worker
                            result = await manager.stop_trading_worker(worker_id)
                            assert result is True

        finally:
            if os.path.exists(strategy_path):
                os.unlink(strategy_path)

    @pytest.mark.asyncio
    async def test_worker_count_limit(self, manager_config):
        """测试 Worker 数量限制"""
        from worker.manager import TradingNodeWorkerManager

        manager_config["max_workers"] = 2

        with patch('worker.manager.WorkerManager.start', new_callable=AsyncMock, return_value=True):
            manager = TradingNodeWorkerManager(**manager_config)
            manager._workers = {"worker-1": Mock(), "worker-2": Mock()}

            # 尝试启动超过限制的 Worker
            result = await manager.start_trading_worker(
                strategy_path="/tmp/test.py",
                config={},
            )

            assert result is None  # 应该返回 None 表示失败

    def test_merge_config(self, manager_config):
        """测试配置合并"""
        from worker.manager import TradingNodeWorkerManager

        with patch('worker.manager.WorkerManager.start', new_callable=AsyncMock, return_value=True):
            manager = TradingNodeWorkerManager(**manager_config)
            manager.trading_config = {"global_setting": "value"}

            base_config = {"local_setting": "local"}
            exchange_config = {"name": "binance", "api_key": "test"}

            merged = manager._merge_config(base_config, exchange_config)

            assert merged["local_setting"] == "local"
            assert "trading" in merged
            assert merged["trading"]["global_setting"] == "value"
            assert "exchange" in merged

    def test_get_trading_node_status(self, manager_config):
        """测试获取 TradingNode 状态"""
        from worker.manager import TradingNodeWorkerManager

        with patch('worker.manager.WorkerManager.start', new_callable=AsyncMock, return_value=True):
            manager = TradingNodeWorkerManager(**manager_config)

            mock_node = Mock()
            mock_node.is_running = True
            mock_node.strategies = [Mock(), Mock()]
            mock_node.portfolio.positions = [Mock()]
            mock_node.clock.timestamp_ns = 1704067200000000000

            status = manager._get_trading_node_status(mock_node)

            assert status["initialized"] is True
            assert status["is_running"] is True
            assert status["strategy_count"] == 2

    def test_register_exchange_adapter(self, manager_config):
        """测试注册交易所适配器"""
        from worker.manager import TradingNodeWorkerManager

        with patch('worker.manager.WorkerManager.start', new_callable=AsyncMock, return_value=True):
            manager = TradingNodeWorkerManager(**manager_config)

            adapter_config = {
                "api_key": "test_key",
                "api_secret": "test_secret",
                "testnet": True,
            }

            manager.register_exchange_adapter("binance", adapter_config)

            assert "binance" in manager.exchange_adapters
            assert manager.exchange_adapters["binance"]["api_key"] == "test_key"


# =============================================================================
# WorkerMonitor 集成测试
# =============================================================================

class TestWorkerMonitorIntegration(TestTradingIntegrationBase):
    """WorkerMonitor 集成测试"""

    @pytest.fixture
    def mock_worker_manager(self):
        """创建模拟 WorkerManager"""
        manager = Mock()
        manager.get_all_workers = Mock(return_value={})
        manager.get_worker_status = Mock(return_value=None)
        manager.get_worker = Mock(return_value=None)
        return manager

    @pytest.mark.asyncio
    async def test_monitor_initialization(self, mock_worker_manager):
        """测试监控器初始化"""
        from worker.manager import WorkerMonitor

        monitor = WorkerMonitor(
            worker_manager=mock_worker_manager,
            check_interval=10,
            metrics_interval=30,
        )

        assert monitor.worker_manager is mock_worker_manager
        assert monitor.check_interval == 10
        assert monitor.metrics_interval == 30
        assert monitor.metrics_collector is not None

    @pytest.mark.asyncio
    async def test_alert_config_management(self, mock_worker_manager):
        """测试告警配置管理"""
        from worker.manager import WorkerMonitor, AlertConfig, AlertRule, AlertRuleType, AlertSeverity

        monitor = WorkerMonitor(worker_manager=mock_worker_manager)

        # 创建告警配置
        config = AlertConfig(
            worker_id="test-worker",
            enabled=True,
            auto_restart_enabled=True,
            max_restart_attempts=3,
        )

        # 添加告警规则
        config.add_rule(AlertRule(
            rule_type=AlertRuleType.MEMORY_USAGE,
            name="high_memory",
            threshold=80.0,
            severity=AlertSeverity.WARNING,
        ))

        # 设置配置
        monitor.set_alert_config("test-worker", config)

        # 验证配置
        retrieved_config = monitor.get_alert_config("test-worker")
        assert retrieved_config is config
        assert len(retrieved_config.rules) == 1
        assert retrieved_config.rules[0].name == "high_memory"

    def test_metrics_collection(self, mock_worker_manager):
        """测试指标收集"""
        from worker.manager import MetricsCollector, WorkerMetrics

        collector = MetricsCollector(max_history=100)

        # 记录延迟数据
        for i in range(10):
            collector.record_latency("test-worker", float(i * 10))

        # 获取历史
        history = collector.get_metrics_history("test-worker", limit=5)
        assert len(history) <= 5

    def test_worker_metrics_dataclass(self):
        """测试 WorkerMetrics 数据类"""
        from worker.manager import WorkerMetrics

        metrics = WorkerMetrics(
            worker_id="test-worker",
            cpu_percent=50.0,
            memory_percent=60.0,
            events_per_second=100.0,
            error_count=5,
        )

        assert metrics.worker_id == "test-worker"
        assert metrics.cpu_percent == 50.0

        # 测试转换为字典
        metrics_dict = metrics.to_dict()
        assert metrics_dict["worker_id"] == "test-worker"
        assert "cpu" in metrics_dict
        assert "memory" in metrics_dict


# =============================================================================
# 端到端集成测试
# =============================================================================

class TestEndToEndIntegration(TestTradingIntegrationBase):
    """端到端集成测试"""

    @pytest.mark.asyncio
    async def test_full_trading_flow(self):
        """测试完整交易流程"""
        from worker.manager import TradingNodeWorkerManager
        from worker.event_handler import EventHandler, EventBufferConfig

        # 创建模拟组件
        mock_node = AsyncMock()
        mock_node.start = AsyncMock()
        mock_node.stop = AsyncMock()
        mock_node.is_running = True

        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('''
from trading_engine.trading.strategy import Strategy
from trading_engine.config import StrategyConfig

class E2EStrategy(Strategy):
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
    
    def on_start(self):
        pass
    
    def on_bar(self, bar):
        pass
''')
            strategy_path = f.name

        try:
            with patch('worker.manager.WorkerManager.start', new_callable=AsyncMock, return_value=True):
                with patch('worker.manager.WorkerManager.stop', new_callable=AsyncMock, return_value=True):
                    with patch('worker.worker_process.TradingNode', return_value=mock_node):
                        with patch('worker.worker_process.build_trading_config', return_value={}):
                            # 创建管理器
                            manager = TradingNodeWorkerManager(
                                max_workers=2,
                                enable_monitoring=True,
                            )

                            # 启动 Worker
                            worker_id = await manager.start_trading_worker(
                                strategy_path=strategy_path,
                                config={"strategy_class": "E2EStrategy"},
                            )

                            assert worker_id is not None

                            # 获取 Worker 状态
                            status = manager.get_trading_worker_status(worker_id)
                            assert status is not None
                            assert status["worker_id"] == worker_id

                            # 停止 Worker
                            result = await manager.stop_trading_worker(worker_id)
                            assert result is True

        finally:
            if os.path.exists(strategy_path):
                os.unlink(strategy_path)

    @pytest.mark.asyncio
    async def test_multiple_workers_management(self):
        """测试多 Worker 管理"""
        from worker.manager import TradingNodeWorkerManager

        with patch('worker.manager.WorkerManager.start', new_callable=AsyncMock, return_value=True):
            manager = TradingNodeWorkerManager(max_workers=5)

            # 模拟多个 Worker
            for i in range(3):
                mock_worker = Mock()
                mock_worker.is_alive = Mock(return_value=True)
                worker_id = f"worker-{i}"
                manager._workers[worker_id] = mock_worker
                manager._trading_workers[worker_id] = mock_worker

            # 验证 Worker 数量
            assert manager.get_trading_worker_count() == 3

            # 获取所有 Worker
            all_workers = manager.get_all_trading_workers()
            assert len(all_workers) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
