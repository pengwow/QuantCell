"""
批处理引擎单元测试

测试范围:
- BatchingEngine 基本功能
- 微批处理（时间触发和大小触发）
- 向量化执行
- 批处理策略
- 性能指标收集
"""

import pytest
import time
import threading
import numpy as np
from unittest.mock import Mock, patch, MagicMock

from strategy.core.batching_engine import (
    BatchingEngine,
    EventBatch,
    BatchStrategy,
    VectorizedBatchProcessor,
    BatchMetrics
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def batching_engine():
    """创建批处理引擎实例"""
    engine = BatchingEngine(
        max_batch_size=100,
        max_wait_time_ms=50,
        max_queue_size=1000
    )
    yield engine
    # 清理
    if engine.running:
        engine.stop()


@pytest.fixture
def running_batching_engine():
    """创建并启动的批处理引擎"""
    engine = BatchingEngine(
        max_batch_size=100,
        max_wait_time_ms=50,
        max_queue_size=1000
    )
    engine.start()
    yield engine
    engine.stop()


@pytest.fixture
def event_batch():
    """创建事件批次实例"""
    return EventBatch(max_size=100)


@pytest.fixture
def batch_strategy():
    """创建批处理策略实例"""
    return BatchStrategy(
        max_batch_size=100,
        max_wait_time_ms=50
    )


@pytest.fixture
def vectorized_processor():
    """创建向量化批处理器实例"""
    return VectorizedBatchProcessor()


# =============================================================================
# BatchingEngine 测试
# =============================================================================

class TestBatchingEngine:
    """批处理引擎测试类"""

    def test_basic_batch_processing(self, batching_engine):
        """测试基本批处理"""
        batches_received = []

        def handler(batch):
            batches_received.append(batch)

        batching_engine.register("TEST", handler)
        batching_engine.start()

        try:
            # 发送单个事件
            batching_engine.put("TEST", "data1")
            time.sleep(0.1)

            assert len(batches_received) >= 1
        finally:
            batching_engine.stop()

    def test_batch_size_trigger(self, batching_engine):
        """测试批次大小触发"""
        batches_received = []

        def handler(batch):
            batches_received.append(batch)

        # 使用小批次大小以便测试
        engine = BatchingEngine(
            max_batch_size=5,
            max_wait_time_ms=5000,  # 长时间等待，确保由大小触发
            max_queue_size=1000
        )
        engine.register("TEST", handler)
        engine.start()

        try:
            # 发送5个事件，应该触发批次
            for i in range(5):
                engine.put("TEST", f"data{i}")

            time.sleep(0.1)

            assert len(batches_received) >= 1
            # 第一个批次应该包含5个事件
            assert len(batches_received[0]) == 5
        finally:
            engine.stop()

    def test_batch_time_trigger(self, batching_engine):
        """测试批次时间触发"""
        batches_received = []

        def handler(batch):
            batches_received.append(batch)

        # 使用短等待时间
        engine = BatchingEngine(
            max_batch_size=1000,  # 大批次大小，确保由时间触发
            max_wait_time_ms=100,  # 100ms等待
            max_queue_size=1000
        )
        engine.register("TEST", handler)
        engine.start()

        try:
            # 发送2个事件
            engine.put("TEST", "data1")
            engine.put("TEST", "data2")

            # 等待时间触发
            time.sleep(0.2)

            assert len(batches_received) >= 1
            # 批次应该包含2个事件
            assert len(batches_received[0]) == 2
        finally:
            engine.stop()

    def test_multiple_handlers(self, batching_engine):
        """测试多个处理器"""
        results = []

        def handler1(batch):
            results.append(("handler1", len(batch)))

        def handler2(batch):
            results.append(("handler2", len(batch)))

        batching_engine.register("TEST", handler1)
        batching_engine.register("TEST", handler2)
        batching_engine.start()

        try:
            batching_engine.put("TEST", "data")
            time.sleep(0.1)

            assert len(results) == 2
        finally:
            batching_engine.stop()

    def test_batch_contents(self, batching_engine):
        """测试批次内容"""
        batches_received = []

        def handler(batch):
            batches_received.append(batch)

        batching_engine.register("TEST", handler)
        batching_engine.start()

        try:
            for i in range(3):
                batching_engine.put("TEST", {"id": i, "value": f"data{i}"})

            time.sleep(0.1)

            assert len(batches_received) >= 1
            batch = batches_received[0]
            assert len(batch) == 3

            # 验证批次中的数据
            values = [item["data"]["value"] for item in batch]
            assert "data0" in values
            assert "data1" in values
            assert "data2" in values
        finally:
            batching_engine.stop()

    def test_metrics_collection(self, batching_engine):
        """测试指标收集"""
        def handler(batch):
            time.sleep(0.01)

        batching_engine.register("TEST", handler)
        batching_engine.start()

        try:
            for i in range(10):
                batching_engine.put("TEST", f"data{i}")

            time.sleep(0.3)

            metrics = batching_engine.get_metrics()
            assert metrics["total_events"] >= 10
            assert metrics["total_batches"] >= 1
            assert "avg_batch_size" in metrics
            assert "avg_processing_time_ms" in metrics
        finally:
            batching_engine.stop()

    def test_handler_exception_isolation(self, batching_engine):
        """测试处理器异常隔离"""
        results = []

        def failing_handler(batch):
            raise ValueError("测试异常")

        def good_handler(batch):
            results.append(len(batch))

        batching_engine.register("FAIL", failing_handler)
        batching_engine.register("GOOD", good_handler)
        batching_engine.start()

        try:
            batching_engine.put("FAIL", "bad_data")
            batching_engine.put("GOOD", "good_data")
            time.sleep(0.2)

            assert len(results) >= 1
        finally:
            batching_engine.stop()

    def test_engine_lifecycle(self, batching_engine):
        """测试引擎生命周期管理"""
        assert not batching_engine.running

        batching_engine.start()
        assert batching_engine.running

        batching_engine.stop()
        assert not batching_engine.running

    def test_double_start_stop(self, batching_engine):
        """测试重复启动和停止"""
        batching_engine.start()
        batching_engine.start()  # 应该安全
        assert batching_engine.running

        batching_engine.stop()
        batching_engine.stop()  # 应该安全
        assert not batching_engine.running

    def test_unregister_handler(self, batching_engine):
        """测试注销处理器"""
        results = []

        def handler(batch):
            results.append(len(batch))

        batching_engine.register("TEST", handler)
        batching_engine.start()

        try:
            batching_engine.put("TEST", "data1")
            time.sleep(0.1)

            batching_engine.unregister("TEST", handler)
            batching_engine.put("TEST", "data2")
            time.sleep(0.1)

            assert len(results) >= 1
        finally:
            batching_engine.stop()

    def test_clear_handlers(self, batching_engine):
        """测试清空处理器"""
        results = []

        def handler(batch):
            results.append(len(batch))

        batching_engine.register("TEST", handler)
        batching_engine.start()

        try:
            batching_engine.put("TEST", "data1")
            time.sleep(0.1)

            batching_engine.clear_handlers("TEST")
            batching_engine.put("TEST", "data2")
            time.sleep(0.1)

            assert len(results) >= 1
        finally:
            batching_engine.stop()

    def test_get_all_handlers(self, batching_engine):
        """测试获取所有处理器"""
        def handler1(batch):
            pass

        def handler2(batch):
            pass

        batching_engine.register("TEST1", handler1)
        batching_engine.register("TEST2", handler2)

        handlers = batching_engine.get_all_handlers()
        assert "TEST1" in handlers
        assert "TEST2" in handlers
        assert len(handlers["TEST1"]) == 1
        assert len(handlers["TEST2"]) == 1

    def test_flush_empty_queue(self, batching_engine):
        """测试刷新空队列"""
        batching_engine.start()

        try:
            # 刷新空队列应该安全
            batching_engine.flush()
            assert True
        finally:
            batching_engine.stop()

    def test_flush_pending_events(self, batching_engine):
        """测试刷新待处理事件"""
        batches_received = []

        def handler(batch):
            batches_received.append(batch)

        batching_engine.register("TEST", handler)
        batching_engine.start()

        try:
            # 发送事件但不等待时间触发
            batching_engine.put("TEST", "data1")
            batching_engine.put("TEST", "data2")

            # 立即刷新
            batching_engine.flush()

            assert len(batches_received) >= 1
        finally:
            batching_engine.stop()


# =============================================================================
# EventBatch 测试
# =============================================================================

class TestEventBatch:
    """事件批次测试类"""

    def test_batch_initialization(self, event_batch):
        """测试批次初始化"""
        assert event_batch.max_size == 100
        assert len(event_batch) == 0
        assert not event_batch.is_full()

    def test_batch_add_event(self, event_batch):
        """测试添加事件到批次"""
        event_batch.add({"type": "TEST", "data": "data1"})
        event_batch.add({"type": "TEST", "data": "data2"})

        assert len(event_batch) == 2

    def test_batch_full(self, event_batch):
        """测试批次满"""
        small_batch = EventBatch(max_size=3)

        small_batch.add({"data": "1"})
        small_batch.add({"data": "2"})
        assert not small_batch.is_full()

        small_batch.add({"data": "3"})
        assert small_batch.is_full()

    def test_batch_clear(self, event_batch):
        """测试清空批次"""
        event_batch.add({"data": "1"})
        event_batch.add({"data": "2"})
        assert len(event_batch) == 2

        event_batch.clear()
        assert len(event_batch) == 0

    def test_batch_iteration(self, event_batch):
        """测试批次迭代"""
        event_batch.add({"data": "1"})
        event_batch.add({"data": "2"})
        event_batch.add({"data": "3"})

        items = list(event_batch)
        assert len(items) == 3
        assert items[0]["data"] == "1"
        assert items[1]["data"] == "2"
        assert items[2]["data"] == "3"

    def test_batch_get_events(self, event_batch):
        """测试获取批次事件"""
        event_batch.add({"data": "1"})
        event_batch.add({"data": "2"})

        events = event_batch.get_events()
        assert len(events) == 2
        assert events[0]["data"] == "1"
        assert events[1]["data"] == "2"


# =============================================================================
# BatchStrategy 测试
# =============================================================================

class TestBatchStrategy:
    """批处理策略测试类"""

    def test_strategy_initialization(self, batch_strategy):
        """测试策略初始化"""
        assert batch_strategy.max_batch_size == 100
        assert batch_strategy.max_wait_time_ms == 50

    def test_should_flush_by_size(self, batch_strategy):
        """测试按大小刷新"""
        batch = EventBatch(max_size=10)

        # 添加9个事件，不应该刷新
        for i in range(9):
            batch.add({"data": i})
        assert not batch_strategy.should_flush(batch)

        # 添加第10个事件，应该刷新
        batch.add({"data": 9})
        assert batch_strategy.should_flush(batch)

    def test_should_flush_by_time(self, batch_strategy):
        """测试按时间刷新"""
        batch = EventBatch(max_size=100)
        batch.add({"data": "1"})

        # 立即检查，不应该刷新
        assert not batch_strategy.should_flush(batch)

        # 等待超过最大等待时间
        time.sleep(0.06)  # 60ms > 50ms
        assert batch_strategy.should_flush(batch)

    def test_should_flush_empty_batch(self, batch_strategy):
        """测试空批次不刷新"""
        batch = EventBatch(max_size=10)
        assert not batch_strategy.should_flush(batch)

    def test_strategy_reset_timer(self, batch_strategy):
        """测试策略重置计时器"""
        batch = EventBatch(max_size=100)
        batch.add({"data": "1"})

        # 等待一段时间
        time.sleep(0.03)

        # 重置计时器
        batch_strategy.reset_timer()

        # 立即检查，不应该刷新（计时器已重置）
        assert not batch_strategy.should_flush(batch)


# =============================================================================
# VectorizedBatchProcessor 测试
# =============================================================================

class TestVectorizedBatchProcessor:
    """向量化批处理器测试类"""

    def test_processor_initialization(self, vectorized_processor):
        """测试处理器初始化"""
        assert vectorized_processor is not None

    def test_process_prices(self, vectorized_processor):
        """测试处理价格数据"""
        batch = [
            {"symbol": "BTCUSDT", "price": 50000.0, "volume": 1.5},
            {"symbol": "BTCUSDT", "price": 50100.0, "volume": 2.0},
            {"symbol": "BTCUSDT", "price": 50200.0, "volume": 1.0},
        ]

        result = vectorized_processor.process_prices(batch)

        assert "mean" in result
        assert "std" in result
        assert "min" in result
        assert "max" in result
        assert result["count"] == 3

    def test_process_empty_batch(self, vectorized_processor):
        """测试处理空批次"""
        result = vectorized_processor.process_prices([])

        assert result["count"] == 0

    def test_process_indicators(self, vectorized_processor):
        """测试处理指标计算"""
        prices = [100.0, 101.0, 102.0, 103.0, 104.0]

        sma = vectorized_processor.calculate_sma(prices, period=3)

        assert len(sma) == len(prices)
        # 前两个值应该是NaN，因为周期不足
        assert np.isnan(sma[0])
        assert np.isnan(sma[1])
        # 第三个值应该是前3个的平均值
        assert sma[2] == pytest.approx(101.0)

    def test_process_returns(self, vectorized_processor):
        """测试处理收益率计算"""
        prices = [100.0, 101.0, 102.0, 103.0]

        returns = vectorized_processor.calculate_returns(prices)

        assert len(returns) == len(prices)
        # 第一个值应该是NaN
        assert np.isnan(returns[0])
        # 后续应该是收益率
        assert returns[1] == pytest.approx(0.01)  # (101-100)/100
        assert returns[2] == pytest.approx(0.00990099, abs=1e-5)


# =============================================================================
# BatchMetrics 测试
# =============================================================================

class TestBatchMetrics:
    """批次指标测试类"""

    def test_metrics_initialization(self):
        """测试指标初始化"""
        metrics = BatchMetrics()
        stats = metrics.get_stats()

        assert stats["total_events"] == 0
        assert stats["total_batches"] == 0
        assert stats["avg_batch_size"] == 0.0

    def test_metrics_record_batch(self):
        """测试记录批次"""
        metrics = BatchMetrics()

        metrics.record_batch(10, 0.05)
        metrics.record_batch(20, 0.1)
        metrics.record_batch(30, 0.15)

        stats = metrics.get_stats()
        assert stats["total_events"] == 60
        assert stats["total_batches"] == 3
        assert stats["avg_batch_size"] == 20.0

    def test_metrics_record_event(self):
        """测试记录单个事件"""
        metrics = BatchMetrics()

        for i in range(100):
            metrics.record_event()

        stats = metrics.get_stats()
        assert stats["total_events"] == 100

    def test_metrics_record_error(self):
        """测试记录错误"""
        metrics = BatchMetrics()

        metrics.record_error()
        metrics.record_error()

        stats = metrics.get_stats()
        assert stats["error_count"] == 2

    def test_metrics_thread_safety(self):
        """测试指标线程安全"""
        metrics = BatchMetrics()

        def record_many():
            for _ in range(100):
                metrics.record_batch(10, 0.01)

        threads = [
            threading.Thread(target=record_many)
            for _ in range(5)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        stats = metrics.get_stats()
        assert stats["total_batches"] == 500
        assert stats["total_events"] == 5000

    def test_metrics_reset(self):
        """测试指标重置"""
        metrics = BatchMetrics()

        metrics.record_batch(10, 0.05)
        metrics.record_error()

        metrics.reset()

        stats = metrics.get_stats()
        assert stats["total_events"] == 0
        assert stats["total_batches"] == 0
        assert stats["error_count"] == 0


# =============================================================================
# 性能基准测试
# =============================================================================

class TestBatchingPerformanceBenchmarks:
    """批处理性能基准测试类"""

    @pytest.mark.slow
    def test_batching_throughput_benchmark(self):
        """测试批处理吞吐量基准"""
        engine = BatchingEngine(
            max_batch_size=100,
            max_wait_time_ms=100,
            max_queue_size=10000
        )
        event_count = 10000
        processed_events = 0
        lock = threading.Lock()

        def handler(batch):
            nonlocal processed_events
            with lock:
                processed_events += len(batch)

        engine.register("BENCH", handler)
        engine.start()

        try:
            start_time = time.time()

            for i in range(event_count):
                engine.put("BENCH", f"data{i}")

            # 等待所有批次处理完成
            time.sleep(0.5)
            engine.flush()
            time.sleep(0.2)

            elapsed = time.time() - start_time
            throughput = processed_events / elapsed

            print(f"\n批处理吞吐量: {throughput:.0f} 事件/秒")
            print(f"处理事件数: {processed_events}/{event_count}")

            assert processed_events == event_count
            assert throughput > 5000
        finally:
            engine.stop()

    @pytest.mark.slow
    def test_batch_size_efficiency(self):
        """测试批次大小效率"""
        batch_sizes = [10, 50, 100, 200]
        results = {}

        for batch_size in batch_sizes:
            engine = BatchingEngine(
                max_batch_size=batch_size,
                max_wait_time_ms=1000,  # 长时间等待，确保由大小触发
                max_queue_size=10000
            )
            batch_count = 0
            lock = threading.Lock()

            def handler(batch):
                nonlocal batch_count
                with lock:
                    batch_count += 1

            engine.register("TEST", handler)
            engine.start()

            try:
                # 发送1000个事件
                for i in range(1000):
                    engine.put("TEST", f"data{i}")

                time.sleep(0.1)
                engine.flush()
                time.sleep(0.1)

                results[batch_size] = batch_count
                print(f"\n批次大小 {batch_size}: {batch_count} 个批次")
            finally:
                engine.stop()

        # 验证批次数量符合预期
        assert results[10] >= 100  # 1000/10 = 100
        assert results[50] >= 20   # 1000/50 = 20
        assert results[100] >= 10  # 1000/100 = 10
        assert results[200] >= 5   # 1000/200 = 5

    @pytest.mark.slow
    def test_vectorized_processing_benchmark(self):
        """测试向量化处理基准"""
        processor = VectorizedBatchProcessor()

        # 创建大批量价格数据
        batch_size = 10000
        batch = [
            {"symbol": "BTCUSDT", "price": 50000.0 + i, "volume": 1.0}
            for i in range(batch_size)
        ]

        start_time = time.time()
        result = processor.process_prices(batch)
        elapsed = time.time() - start_time

        throughput = batch_size / elapsed

        print(f"\n向量化处理吞吐量: {throughput:.0f} 事件/秒")
        print(f"处理时间: {elapsed*1000:.2f} ms")

        assert result["count"] == batch_size
        assert elapsed < 1.0  # 应该在1秒内完成

    @pytest.mark.slow
    def test_latency_vs_batch_size(self):
        """测试延迟与批次大小的关系"""
        latencies = {}

        for batch_size in [10, 50, 100]:
            engine = BatchingEngine(
                max_batch_size=batch_size,
                max_wait_time_ms=1000,  # 长时间等待
                max_queue_size=1000
            )
            latencies_list = []
            lock = threading.Lock()

            def handler(batch):
                # 计算批次中事件的平均延迟
                now = time.time()
                for item in batch:
                    latency = now - item["timestamp"]
                    with lock:
                        latencies_list.append(latency)

            engine.register("LATENCY", handler)
            engine.start()

            try:
                start_time = time.time()

                # 发送事件
                for i in range(batch_size):
                    engine.put("LATENCY", {"timestamp": time.time()})

                # 等待批次处理
                time.sleep(0.1)
                engine.flush()
                time.sleep(0.1)

                if latencies_list:
                    avg_latency = sum(latencies_list) / len(latencies_list) * 1000
                    latencies[batch_size] = avg_latency
                    print(f"\n批次大小 {batch_size}: 平均延迟 {avg_latency:.2f} ms")
            finally:
                engine.stop()

        # 验证延迟数据已收集
        assert len(latencies) > 0
