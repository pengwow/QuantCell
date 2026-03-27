# -*- coding: utf-8 -*-
"""
Nautilus Worker 性能测试

测试 Nautilus Worker 的性能指标，包括：
- 订单延迟测试
- 事件处理吞吐量
- 内存使用测试
- 并发 Worker 性能

使用 pytest-benchmark 进行基准测试，使用 pytest-asyncio 支持异步测试
"""

import pytest
import asyncio
import time
import gc
import psutil
import os
from datetime import datetime
from unittest.mock import Mock, AsyncMock, MagicMock, patch
from typing import Dict, Any, List
from collections import deque
import sys

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../..'))


# =============================================================================
# 性能测试基类
# =============================================================================

class TestNautilusPerformanceBase:
    """Nautilus 性能测试基类"""

    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        """测试前后设置和清理"""
        # 测试前强制垃圾回收
        gc.collect()
        self.process = psutil.Process(os.getpid())
        self.start_memory = self.process.memory_info().rss / 1024 / 1024  # MB
        self.start_time = time.perf_counter()
        yield
        # 测试后清理
        gc.collect()
        end_memory = self.process.memory_info().rss / 1024 / 1024  # MB
        end_time = time.perf_counter()
        duration = end_time - self.start_time
        memory_diff = end_memory - self.start_memory
        print(f"\n测试耗时: {duration:.3f}s, 内存变化: {memory_diff:.2f}MB")


# =============================================================================
# 订单延迟测试
# =============================================================================

class TestOrderLatency(TestNautilusPerformanceBase):
    """订单延迟性能测试"""

    @pytest.mark.benchmark
    def test_order_conversion_latency(self, benchmark):
        """测试订单转换延迟"""
        from strategy.nautilus_adapter import convert_order_to_nautilus
        from strategy.core.data_types import InstrumentId, OrderSide, OrderType, TimeInForce
        from decimal import Decimal

        qc_order = {
            "instrument_id": InstrumentId("BTCUSDT", "BINANCE"),
            "side": OrderSide.BUY,
            "order_type": OrderType.LIMIT,
            "quantity": Decimal("0.1"),
            "price": Decimal("50000"),
            "time_in_force": TimeInForce.GTC,
        }

        # 使用 pytest-benchmark 测量性能
        result = benchmark(convert_order_to_nautilus, qc_order)
        assert result is not None

    @pytest.mark.benchmark
    def test_fill_event_conversion_latency(self, benchmark):
        """测试成交事件转换延迟"""
        from worker.nautilus_event_handler import convert_fill_to_qc
        from nautilus_trader.execution.messages import OrderFilled

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

        result = benchmark(convert_fill_to_qc, mock_fill)
        assert result["event_type"] == "fill"

    @pytest.mark.asyncio
    async def test_event_send_latency(self):
        """测试事件发送延迟"""
        from worker.nautilus_event_handler import NautilusEventHandler, EventBufferConfig

        mock_comm_client = AsyncMock()
        mock_comm_client.send_status = AsyncMock(return_value=True)

        config = EventBufferConfig()

        with patch('worker.nautilus_event_handler.Actor.__init__', return_value=None):
            handler = NautilusEventHandler(
                worker_id="perf-test",
                comm_client=mock_comm_client,
                buffer_config=config,
            )

            latencies = []
            for i in range(100):
                start = time.perf_counter()
                await handler.send_event("test", {"index": i})
                end = time.perf_counter()
                latencies.append((end - start) * 1000)  # 转换为毫秒

            avg_latency = sum(latencies) / len(latencies)
            max_latency = max(latencies)
            p95_latency = sorted(latencies)[int(len(latencies) * 0.95)]

            print(f"\n事件发送延迟 - 平均: {avg_latency:.3f}ms, P95: {p95_latency:.3f}ms, 最大: {max_latency:.3f}ms")

            # 断言性能要求
            assert avg_latency < 10.0  # 平均延迟应小于 10ms
            assert p95_latency < 20.0  # P95 延迟应小于 20ms


# =============================================================================
# 事件处理吞吐量测试
# =============================================================================

class TestEventThroughput(TestNautilusPerformanceBase):
    """事件处理吞吐量测试"""

    @pytest.mark.asyncio
    async def test_event_buffer_throughput(self):
        """测试事件缓冲吞吐量"""
        from worker.nautilus_event_handler import NautilusEventHandler, EventBufferConfig

        mock_comm_client = AsyncMock()
        mock_comm_client.send_status = AsyncMock(return_value=True)

        config = EventBufferConfig(
            buffer_size=10000,
            max_batch_size=100,
        )

        with patch('worker.nautilus_event_handler.Actor.__init__', return_value=None):
            handler = NautilusEventHandler(
                worker_id="throughput-test",
                comm_client=mock_comm_client,
                buffer_config=config,
            )

            event_count = 10000
            start_time = time.perf_counter()

            # 批量添加事件
            for i in range(event_count):
                handler._buffer_event("fill", {
                    "order_id": f"order-{i}",
                    "symbol": "BTCUSDT",
                    "price": 50000.0 + i,
                })

            end_time = time.perf_counter()
            duration = end_time - start_time
            throughput = event_count / duration

            print(f"\n事件缓冲吞吐量: {throughput:.0f} events/s")
            assert throughput > 10000  # 吞吐量应大于 10000 events/s

    @pytest.mark.asyncio
    async def test_batch_event_processing_throughput(self):
        """测试批量事件处理吞吐量"""
        from worker.nautilus_event_handler import NautilusEventHandler, EventBufferConfig

        mock_comm_client = AsyncMock()
        mock_comm_client.send_status = AsyncMock(return_value=True)

        config = EventBufferConfig(max_batch_size=100)

        with patch('worker.nautilus_event_handler.Actor.__init__', return_value=None):
            handler = NautilusEventHandler(
                worker_id="batch-test",
                comm_client=mock_comm_client,
                buffer_config=config,
            )

            # 准备批量事件
            events = [
                {"type": "fill", "data": {"order_id": f"order-{i}"}}
                for i in range(1000)
            ]

            start_time = time.perf_counter()
            result = await handler.batch_send_events(events)
            end_time = time.perf_counter()

            duration = end_time - start_time
            throughput = len(events) / duration

            print(f"\n批量事件处理吞吐量: {throughput:.0f} events/s")
            assert result is True
            assert throughput > 1000  # 吞吐量应大于 1000 events/s

    @pytest.mark.benchmark
    def test_bar_conversion_throughput(self, benchmark):
        """测试 K 线数据转换吞吐量"""
        from strategy.nautilus_adapter import convert_bar_to_qc

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
        mock_bar.ts_event = 1704067200000000000

        # 多次转换以测量吞吐量
        def convert_multiple():
            for _ in range(1000):
                convert_bar_to_qc(mock_bar)

        benchmark(convert_multiple)

    @pytest.mark.benchmark
    def test_position_conversion_throughput(self, benchmark):
        """测试持仓数据转换吞吐量"""
        from strategy.nautilus_adapter import convert_position_to_qc
        from nautilus_trader.model.position import Position
        from nautilus_trader.model.enums import PositionSide
        from decimal import Decimal

        mock_position = Mock(spec=Position)
        mock_position.instrument_id.symbol = "BTCUSDT"
        mock_position.instrument_id.venue = "BINANCE"
        mock_position.side = PositionSide.LONG
        mock_position.quantity.as_decimal.return_value = Decimal("0.5")
        mock_position.avg_px_open = 50000.0
        mock_position.unrealized_pnl = 100.0
        mock_position.realized_pnl = 50.0
        mock_position.ts_opened = 1704067200000000000
        mock_position.is_open = True

        def convert_multiple():
            for _ in range(1000):
                convert_position_to_qc(mock_position)

        benchmark(convert_multiple)


# =============================================================================
# 内存使用测试
# =============================================================================

class TestMemoryUsage(TestNautilusPerformanceBase):
    """内存使用测试"""

    def test_event_buffer_memory_usage(self):
        """测试事件缓冲内存使用"""
        from worker.nautilus_event_handler import NautilusEventHandler, EventBufferConfig

        gc.collect()
        initial_memory = psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024

        mock_comm_client = Mock()

        config = EventBufferConfig(buffer_size=100000)

        with patch('worker.nautilus_event_handler.Actor.__init__', return_value=None):
            handler = NautilusEventHandler(
                worker_id="memory-test",
                comm_client=mock_comm_client,
                buffer_config=config,
            )

            # 添加大量事件
            for i in range(50000):
                handler._buffer_event("fill", {
                    "order_id": f"order-{i}",
                    "symbol": "BTCUSDT",
                    "price": 50000.0,
                    "quantity": 0.1,
                    "timestamp": datetime.now().isoformat(),
                    "extra_data": "x" * 100,  # 添加一些额外数据
                })

            gc.collect()
            final_memory = psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024
            memory_used = final_memory - initial_memory
            memory_per_event = memory_used * 1024 / len(handler._event_buffer)  # KB per event

            print(f"\n事件缓冲内存使用: {memory_used:.2f}MB, 每事件: {memory_per_event:.3f}KB")

            # 断言内存使用合理
            assert memory_per_event < 1.0  # 每个事件应小于 1KB

    def test_metrics_collector_memory_usage(self):
        """测试指标收集器内存使用"""
        from worker.nautilus_manager import MetricsCollector, WorkerMetrics

        gc.collect()
        initial_memory = psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024

        collector = MetricsCollector(max_history=10000)

        # 记录大量指标
        for i in range(5000):
            metrics = WorkerMetrics(
                worker_id="test-worker",
                cpu_percent=float(i % 100),
                memory_percent=float(i % 80),
                events_per_second=float(i * 10),
            )
            if "test-worker" not in collector._metrics_history:
                collector._metrics_history["test-worker"] = deque(maxlen=10000)
            collector._metrics_history["test-worker"].append(metrics)

        gc.collect()
        final_memory = psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024
        memory_used = final_memory - initial_memory
        memory_per_metric = memory_used * 1024 / 5000  # KB per metric

        print(f"\n指标收集器内存使用: {memory_used:.2f}MB, 每指标: {memory_per_metric:.3f}KB")

        assert memory_per_metric < 0.5  # 每个指标应小于 0.5KB

    @pytest.mark.asyncio
    async def test_worker_memory_leak(self):
        """测试 Worker 内存泄漏"""
        from worker.nautilus_worker import NautilusWorkerProcess

        gc.collect()
        initial_memory = psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024

        # 创建和销毁多个 Worker 实例
        for i in range(10):
            worker = NautilusWorkerProcess(
                worker_id=f"test-worker-{i}",
                strategy_path="/tmp/test.py",
                config={"nautilus": {}},
            )
            # 模拟一些操作
            worker.status.update_message(f"Test {i}")
            del worker

        gc.collect()
        final_memory = psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024
        memory_growth = final_memory - initial_memory

        print(f"\nWorker 内存增长: {memory_growth:.2f}MB")

        # 断言没有明显内存泄漏
        assert memory_growth < 50  # 内存增长应小于 50MB


# =============================================================================
# 并发 Worker 性能测试
# =============================================================================

class TestConcurrentWorkerPerformance(TestNautilusPerformanceBase):
    """并发 Worker 性能测试"""

    @pytest.mark.asyncio
    async def test_concurrent_event_handling(self):
        """测试并发事件处理"""
        from worker.nautilus_event_handler import NautilusEventHandler, EventBufferConfig

        mock_comm_client = AsyncMock()
        mock_comm_client.send_status = AsyncMock(return_value=True)

        config = EventBufferConfig()

        with patch('worker.nautilus_event_handler.Actor.__init__', return_value=None):
            handler = NautilusEventHandler(
                worker_id="concurrent-test",
                comm_client=mock_comm_client,
                buffer_config=config,
            )

            async def send_events(worker_id: str, count: int):
                """发送事件任务"""
                for i in range(count):
                    await handler.send_event("fill", {
                        "worker_id": worker_id,
                        "index": i,
                    })

            start_time = time.perf_counter()

            # 并发执行多个任务
            await asyncio.gather(
                send_events("worker-1", 100),
                send_events("worker-2", 100),
                send_events("worker-3", 100),
                send_events("worker-4", 100),
            )

            end_time = time.perf_counter()
            duration = end_time - start_time
            total_events = 400
            throughput = total_events / duration

            print(f"\n并发事件处理吞吐量: {throughput:.0f} events/s")
            assert throughput > 500  # 并发吞吐量应大于 500 events/s

    @pytest.mark.asyncio
    async def test_concurrent_worker_operations(self):
        """测试并发 Worker 操作"""
        from worker.nautilus_manager import NautilusWorkerManager

        with patch('worker.manager.WorkerManager.start', new_callable=AsyncMock, return_value=True):
            manager = NautilusWorkerManager(max_workers=10)

            async def simulate_worker_operations(worker_id: str):
                """模拟 Worker 操作"""
                # 模拟状态更新
                for i in range(50):
                    await asyncio.sleep(0.001)  # 模拟操作延迟
                return worker_id

            start_time = time.perf_counter()

            # 并发执行多个 Worker 操作
            tasks = [
                simulate_worker_operations(f"worker-{i}")
                for i in range(5)
            ]
            results = await asyncio.gather(*tasks)

            end_time = time.perf_counter()
            duration = end_time - start_time

            print(f"\n并发 Worker 操作耗时: {duration:.3f}s")
            assert len(results) == 5
            assert duration < 1.0  # 应在 1 秒内完成

    @pytest.mark.asyncio
    async def test_metrics_collection_performance(self):
        """测试指标收集性能"""
        from worker.nautilus_manager import MetricsCollector, WorkerMetrics

        collector = MetricsCollector(max_history=1000)

        async def collect_metrics_batch(worker_ids: List[str], count: int):
            """批量收集指标"""
            for _ in range(count):
                for worker_id in worker_ids:
                    metrics = WorkerMetrics(
                        worker_id=worker_id,
                        cpu_percent=50.0,
                        memory_percent=60.0,
                    )
                    if worker_id not in collector._metrics_history:
                        collector._metrics_history[worker_id] = deque(maxlen=1000)
                    collector._metrics_history[worker_id].append(metrics)
                await asyncio.sleep(0)  # 让出控制权

        worker_ids = [f"worker-{i}" for i in range(10)]

        start_time = time.perf_counter()
        await collect_metrics_batch(worker_ids, 100)
        end_time = time.perf_counter()

        duration = end_time - start_time
        total_metrics = 10 * 100
        throughput = total_metrics / duration

        print(f"\n指标收集吞吐量: {throughput:.0f} metrics/s")
        assert throughput > 1000  # 指标收集吞吐量应大于 1000 metrics/s


# =============================================================================
# 配置构建性能测试
# =============================================================================

class TestConfigBuildPerformance(TestNautilusPerformanceBase):
    """配置构建性能测试"""

    @pytest.mark.benchmark
    def test_build_nautilus_config_performance(self, benchmark):
        """测试 Nautilus 配置构建性能"""
        from worker.nautilus_config import build_nautilus_config

        config = {
            "trader_id": "PERF-TEST-001",
            "environment": "SANDBOX",
            "data_engine": {
                "time_bars_enabled": True,
                "time_bars_interval": 60,
            },
            "risk_engine": {
                "max_order_rate": (100, 60),
            },
            "exec_engine": {
                "reconciliation": True,
            },
            "data_clients": {
                "binance": {
                    "api_key": "test_key",
                    "api_secret": "test_secret",
                    "testnet": True,
                }
            },
            "exec_clients": {
                "binance": {
                    "api_key": "test_key",
                    "api_secret": "test_secret",
                    "testnet": True,
                }
            },
        }

        result = benchmark(build_nautilus_config, config)
        assert result is not None

    @pytest.mark.benchmark
    def test_build_binance_config_performance(self, benchmark):
        """测试 Binance 配置构建性能"""
        from worker.nautilus_config import build_binance_config

        def build_multiple():
            for i in range(100):
                build_binance_config(
                    api_key=f"api_key_{i}",
                    api_secret=f"api_secret_{i}",
                    testnet=True,
                    use_usdt_margin=True,
                )

        benchmark(build_multiple)


# =============================================================================
# 数据转换性能测试
# =============================================================================

class TestDataConversionPerformance(TestNautilusPerformanceBase):
    """数据转换性能测试"""

    @pytest.mark.benchmark
    def test_tick_conversion_performance(self, benchmark):
        """测试 Tick 数据转换性能"""
        from strategy.nautilus_adapter import convert_tick_to_qc
        from nautilus_trader.model.data import QuoteTick

        mock_tick = Mock(spec=QuoteTick)
        mock_tick.instrument_id.symbol = "BTCUSDT"
        mock_tick.instrument_id.venue = "BINANCE"
        mock_tick.bid_price = 50000.0
        mock_tick.bid_size = 1.0
        mock_tick.ask_price = 50001.0
        mock_tick.ask_size = 1.5
        mock_tick.ts_event = 1704067200000000000

        def convert_multiple():
            with patch('strategy.nautilus_adapter.NautilusQuoteTick', QuoteTick):
                for _ in range(1000):
                    convert_tick_to_qc(mock_tick)

        benchmark(convert_multiple)

    @pytest.mark.benchmark
    def test_position_event_conversion_performance(self, benchmark):
        """测试持仓事件转换性能"""
        from worker.nautilus_event_handler import convert_position_event_to_qc
        from nautilus_trader.model.events.position import PositionChanged

        mock_event = Mock(spec=PositionChanged)
        mock_event.id = "event-001"
        mock_event.timestamp_ns = 1704067200000000000
        mock_event.position_id = "pos-001"
        mock_event.instrument_id = "BTCUSDT.BINANCE"
        mock_event.venue = "BINANCE"
        mock_event.strategy_id = "strategy-001"
        mock_event.position.side = "LONG"
        mock_event.position.quantity = 0.5
        mock_event.position.avg_px_open = 50000.0
        mock_event.position.unrealized_pnl = 100.0
        mock_event.position.realized_pnl = 50.0

        def convert_multiple():
            for _ in range(1000):
                convert_position_event_to_qc(mock_event)

        benchmark(convert_multiple)


# =============================================================================
# 端到端性能测试
# =============================================================================

class TestEndToEndPerformance(TestNautilusPerformanceBase):
    """端到端性能测试"""

    @pytest.mark.asyncio
    async def test_full_event_pipeline(self):
        """测试完整事件处理管道"""
        from worker.nautilus_event_handler import (
            NautilusEventHandler, EventBufferConfig,
            convert_fill_to_qc, convert_order_event_to_qc
        )
        from nautilus_trader.execution.messages import OrderFilled, OrderAccepted

        mock_comm_client = AsyncMock()
        mock_comm_client.send_status = AsyncMock(return_value=True)

        config = EventBufferConfig(
            buffer_size=10000,
            flush_interval=0.1,
            max_batch_size=100,
        )

        with patch('worker.nautilus_event_handler.Actor.__init__', return_value=None):
            handler = NautilusEventHandler(
                worker_id="e2e-perf-test",
                comm_client=mock_comm_client,
                buffer_config=config,
            )

            # 创建模拟事件
            events = []
            for i in range(1000):
                mock_fill = Mock(spec=OrderFilled)
                mock_fill.id = f"fill-{i}"
                mock_fill.timestamp_ns = 1704067200000000000 + i * 1000000
                mock_fill.client_order_id = f"order-{i}"
                mock_fill.trade_id = f"trade-{i}"
                mock_fill.instrument_id = "BTCUSDT.BINANCE"
                mock_fill.venue = "BINANCE"
                mock_fill.order_side = "BUY"
                mock_fill.order_type = "LIMIT"
                mock_fill.last_qty = 0.1
                mock_fill.last_px = 50000.0 + i
                mock_fill.commission = 0.001
                mock_fill.commission_currency = "BTC"
                mock_fill.liquidity_side = "MAKER"
                mock_fill.position_id = f"pos-{i}"
                mock_fill.strategy_id = "strategy-001"

                qc_event = convert_fill_to_qc(mock_fill)
                events.append(qc_event)

            start_time = time.perf_counter()

            # 处理所有事件
            for event in events:
                handler._buffer_event("fill", event)

            # 刷新缓冲
            await handler._flush_buffer()

            end_time = time.perf_counter()
            duration = end_time - start_time
            throughput = len(events) / duration

            print(f"\n完整事件管道吞吐量: {throughput:.0f} events/s")
            assert throughput > 5000  # 端到端吞吐量应大于 5000 events/s

    @pytest.mark.asyncio
    async def test_worker_manager_scalability(self):
        """测试 WorkerManager 可扩展性"""
        from worker.nautilus_manager import NautilusWorkerManager

        with patch('worker.manager.WorkerManager.start', new_callable=AsyncMock, return_value=True):
            manager = NautilusWorkerManager(max_workers=20)

            # 模拟添加多个 Worker
            start_time = time.perf_counter()

            for i in range(20):
                mock_worker = Mock()
                mock_worker.is_alive = Mock(return_value=True)
                worker_id = f"scalability-worker-{i}"
                manager._workers[worker_id] = mock_worker
                manager._nautilus_workers[worker_id] = mock_worker

            end_time = time.perf_counter()
            setup_duration = end_time - start_time

            # 测试获取所有 Worker 状态
            start_time = time.perf_counter()
            all_workers = manager.get_all_nautilus_workers()
            end_time = time.perf_counter()
            query_duration = end_time - start_time

            print(f"\nWorkerManager 可扩展性 - 设置: {setup_duration:.3f}s, 查询: {query_duration:.3f}s")
            assert len(all_workers) == 20
            assert query_duration < 0.1  # 查询应在 100ms 内完成


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
