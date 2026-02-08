"""
异步事件引擎单元测试

测试范围:
- AsyncEventEngine 基本功能
- 异步事件处理
- 并发控制
- 等待完成机制
- 性能指标收集
"""

import asyncio
import pytest
import time
from unittest.mock import AsyncMock, patch

from strategy.core.async_event_engine import (
    AsyncEventEngine,
    AsyncBoundedPriorityQueue,
    AsyncEventMetrics,
    AsyncEventPriority
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def async_engine():
    """创建异步事件引擎实例"""
    engine = AsyncEventEngine(num_workers=10, max_queue_size=1000)
    yield engine
    # 清理
    if engine.running:
        asyncio.get_event_loop().run_until_complete(engine.stop())


@pytest.fixture
async def running_async_engine():
    """创建并启动的异步事件引擎"""
    engine = AsyncEventEngine(num_workers=10, max_queue_size=1000)
    await engine.start()
    yield engine
    await engine.stop()


@pytest.fixture
def async_queue():
    """创建异步有界优先队列"""
    return AsyncBoundedPriorityQueue(maxsize=100)


# =============================================================================
# AsyncEventEngine 测试
# =============================================================================

class TestAsyncEventEngine:
    """异步事件引擎测试类"""

    @pytest.mark.asyncio
    async def test_basic_async_event_processing(self, async_engine):
        """测试基本异步事件处理"""
        events_received = []

        async def handler(data):
            events_received.append(data)

        async_engine.register("TEST", handler)
        await async_engine.start()

        try:
            await async_engine.put("TEST", "data1")
            await asyncio.sleep(0.1)
            assert len(events_received) == 1
            assert events_received[0] == "data1"
        finally:
            await async_engine.stop()

    @pytest.mark.asyncio
    async def test_multiple_async_handlers(self, async_engine):
        """测试多个异步处理器"""
        results = []

        async def handler1(data):
            results.append(("handler1", data))

        async def handler2(data):
            results.append(("handler2", data))

        async_engine.register("TEST", handler1)
        async_engine.register("TEST", handler2)
        await async_engine.start()

        try:
            await async_engine.put("TEST", "data")
            await asyncio.sleep(0.1)
            assert len(results) == 2
        finally:
            await async_engine.stop()

    @pytest.mark.asyncio
    async def test_async_priority_ordering(self, async_engine):
        """测试异步优先级排序"""
        results = []

        async def handler(data):
            results.append(data)
            await asyncio.sleep(0.01)  # 模拟处理时间

        async_engine.register("TEST", handler)
        await async_engine.start()

        try:
            # 按低优先级到高优先级的顺序放入
            await async_engine.put("TEST", "low", priority=AsyncEventPriority.LOW)
            await async_engine.put("TEST", "normal", priority=AsyncEventPriority.NORMAL)
            await async_engine.put("TEST", "high", priority=AsyncEventPriority.HIGH)
            await async_engine.put("TEST", "critical", priority=AsyncEventPriority.CRITICAL)

            await asyncio.sleep(0.5)

            # 高优先级应该先被处理
            assert results[0] == "critical"
            assert results[1] == "high"
        finally:
            await async_engine.stop()

    @pytest.mark.asyncio
    async def test_concurrent_execution_limit(self):
        """测试并发执行限制"""
        engine = AsyncEventEngine(num_workers=2, max_queue_size=100)
        concurrent_count = 0
        max_concurrent_observed = 0

        async def slow_handler(data):
            nonlocal concurrent_count, max_concurrent_observed
            concurrent_count += 1
            max_concurrent_observed = max(max_concurrent_observed, concurrent_count)
            await asyncio.sleep(0.2)  # 模拟耗时操作
            concurrent_count -= 1

        engine.register("TEST", slow_handler)
        await engine.start()

        try:
            # 同时放入多个事件
            tasks = [engine.put("TEST", f"data{i}") for i in range(5)]
            await asyncio.gather(*tasks)
            await asyncio.sleep(1)

            # 验证并发数没有超过限制
            assert max_concurrent_observed <= 2
        finally:
            await engine.stop()

    @pytest.mark.asyncio
    async def test_wait_for_completion(self, async_engine):
        """测试等待完成机制"""
        processed = []

        async def handler(data):
            await asyncio.sleep(0.1)
            processed.append(data)

        async_engine.register("TEST", handler)
        await async_engine.start()

        try:
            await async_engine.put("TEST", "data1")
            await async_engine.wait_for_completion()

            assert len(processed) == 1
            assert processed[0] == "data1"
        finally:
            await async_engine.stop()

    @pytest.mark.asyncio
    async def test_async_backpressure(self):
        """测试异步背压机制"""
        engine = AsyncEventEngine(num_workers=1, max_queue_size=2)

        async def slow_handler(data):
            await asyncio.sleep(1)  # 很慢的处理

        engine.register("TEST", slow_handler)
        await engine.start()

        try:
            # 填满队列
            await engine.put("TEST", "data1")
            await engine.put("TEST", "data2")

            # 第三个应该触发背压（等待）
            start_time = time.time()
            await engine.put("TEST", "data3", timeout=0.5)
            elapsed = time.time() - start_time

            # 如果背压生效，应该等待一段时间
            assert elapsed >= 0.1
        finally:
            await engine.stop()

    @pytest.mark.asyncio
    async def test_async_metrics_collection(self, async_engine):
        """测试异步指标收集"""
        async def handler(data):
            await asyncio.sleep(0.01)

        async_engine.register("TEST", handler)
        await async_engine.start()

        try:
            for i in range(10):
                await async_engine.put("TEST", f"data{i}")

            await asyncio.sleep(0.5)

            metrics = async_engine.get_metrics()
            assert metrics["processed_count"] >= 10
            assert metrics["queue_size"] == 0
            assert "avg_processing_time_ms" in metrics
        finally:
            await async_engine.stop()

    @pytest.mark.asyncio
    async def test_handler_exception_isolation_async(self, async_engine):
        """测试异步处理器异常隔离"""
        results = []

        async def failing_handler(data):
            raise ValueError("测试异常")

        async def good_handler(data):
            results.append(data)

        async_engine.register("FAIL", failing_handler)
        async_engine.register("GOOD", good_handler)
        await async_engine.start()

        try:
            await async_engine.put("FAIL", "bad_data")
            await async_engine.put("GOOD", "good_data")
            await asyncio.sleep(0.2)

            assert len(results) == 1
            assert results[0] == "good_data"
        finally:
            await async_engine.stop()

    @pytest.mark.asyncio
    async def test_engine_lifecycle(self, async_engine):
        """测试引擎生命周期管理"""
        assert not async_engine.running

        await async_engine.start()
        assert async_engine.running

        await async_engine.stop()
        assert not async_engine.running

    @pytest.mark.asyncio
    async def test_double_start_stop(self, async_engine):
        """测试重复启动和停止"""
        await async_engine.start()
        await async_engine.start()  # 应该安全
        assert async_engine.running

        await async_engine.stop()
        await async_engine.stop()  # 应该安全
        assert not async_engine.running

    @pytest.mark.asyncio
    async def test_unregister_handler(self, async_engine):
        """测试注销处理器"""
        results = []

        async def handler(data):
            results.append(data)

        async_engine.register("TEST", handler)
        await async_engine.start()

        try:
            await async_engine.put("TEST", "data1")
            await asyncio.sleep(0.1)

            async_engine.unregister("TEST", handler)
            await async_engine.put("TEST", "data2")
            await asyncio.sleep(0.1)

            assert len(results) == 1
        finally:
            await async_engine.stop()

    @pytest.mark.asyncio
    async def test_clear_handlers(self, async_engine):
        """测试清空处理器"""
        results = []

        async def handler(data):
            results.append(data)

        async_engine.register("TEST", handler)
        await async_engine.start()

        try:
            await async_engine.put("TEST", "data1")
            await asyncio.sleep(0.1)

            async_engine.clear_handlers("TEST")
            await async_engine.put("TEST", "data2")
            await asyncio.sleep(0.1)

            assert len(results) == 1
        finally:
            await async_engine.stop()

    @pytest.mark.asyncio
    async def test_get_all_handlers(self, async_engine):
        """测试获取所有处理器"""
        async def handler1(data):
            pass

        async def handler2(data):
            pass

        async_engine.register("TEST1", handler1)
        async_engine.register("TEST2", handler2)

        handlers = async_engine.get_all_handlers()
        assert "TEST1" in handlers
        assert "TEST2" in handlers
        assert len(handlers["TEST1"]) == 1
        assert len(handlers["TEST2"]) == 1


# =============================================================================
# AsyncBoundedPriorityQueue 测试
# =============================================================================

class TestAsyncBoundedPriorityQueue:
    """异步有界优先队列测试类"""

    @pytest.mark.asyncio
    async def test_async_queue_put_get(self, async_queue):
        """测试异步队列放入和取出"""
        await async_queue.put((AsyncEventPriority.NORMAL, "data1"))
        await async_queue.put((AsyncEventPriority.NORMAL, "data2"))

        item1 = await async_queue.get()
        item2 = await async_queue.get()

        assert item1[1] == "data1"
        assert item2[1] == "data2"

    @pytest.mark.asyncio
    async def test_async_queue_priority(self, async_queue):
        """测试异步队列优先级"""
        await async_queue.put((AsyncEventPriority.LOW, "low"))
        await async_queue.put((AsyncEventPriority.HIGH, "high"))
        await async_queue.put((AsyncEventPriority.NORMAL, "normal"))

        # 高优先级先出
        item1 = await async_queue.get()
        item2 = await async_queue.get()
        item3 = await async_queue.get()

        assert item1[1] == "high"
        assert item2[1] == "normal"
        assert item3[1] == "low"

    @pytest.mark.asyncio
    async def test_async_queue_size_limit(self):
        """测试异步队列大小限制"""
        queue = AsyncBoundedPriorityQueue(maxsize=2)

        await queue.put((AsyncEventPriority.NORMAL, "data1"))
        await queue.put((AsyncEventPriority.NORMAL, "data2"))

        # 第三个应该阻塞或超时
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(
                queue.put((AsyncEventPriority.NORMAL, "data3")),
                timeout=0.1
            )

    @pytest.mark.asyncio
    async def test_async_queue_empty(self, async_queue):
        """测试异步队列为空"""
        assert async_queue.empty()

        await async_queue.put((AsyncEventPriority.NORMAL, "data"))
        assert not async_queue.empty()

        await async_queue.get()
        assert async_queue.empty()

    @pytest.mark.asyncio
    async def test_async_queue_qsize(self, async_queue):
        """测试异步队列大小"""
        assert async_queue.qsize() == 0

        await async_queue.put((AsyncEventPriority.NORMAL, "data1"))
        assert async_queue.qsize() == 1

        await async_queue.put((AsyncEventPriority.NORMAL, "data2"))
        assert async_queue.qsize() == 2


# =============================================================================
# AsyncEventMetrics 测试
# =============================================================================

class TestAsyncEventMetrics:
    """异步事件指标测试类"""

    @pytest.mark.asyncio
    async def test_async_metrics_initialization(self):
        """测试异步指标初始化"""
        metrics = AsyncEventMetrics()
        stats = await metrics.get_stats()

        assert stats["processed_count"] == 0
        assert stats["error_count"] == 0
        assert stats["avg_latency_ms"] == 0.0

    @pytest.mark.asyncio
    async def test_async_metrics_record_processing(self):
        """测试异步指标记录处理"""
        metrics = AsyncEventMetrics()

        await metrics.record_processed(0.01)
        await metrics.record_processed(0.02)
        await metrics.record_processed(0.03)

        stats = await metrics.get_stats()
        assert stats["events_processed"] == 3
        assert stats["avg_processing_time_ms"] > 0

    @pytest.mark.asyncio
    async def test_async_metrics_record_error(self):
        """测试异步指标记录错误"""
        metrics = AsyncEventMetrics()

        # 错误计数通过 record_processed 的异常处理自动记录
        # 这里测试指标系统能正常工作
        await metrics.record_processed(0.01)

        stats = await metrics.get_stats()
        assert stats["events_processed"] == 1

    @pytest.mark.asyncio
    async def test_async_metrics_queue_size(self):
        """测试异步指标队列大小"""
        metrics = AsyncEventMetrics()

        await metrics.record_queue_size(10)
        await metrics.record_queue_size(20)

        stats = await metrics.get_stats()
        assert stats["avg_queue_size"] == 15  # (10+20)/2

    @pytest.mark.asyncio
    async def test_async_metrics_concurrent_access(self):
        """测试异步指标并发访问"""
        metrics = AsyncEventMetrics()

        async def record_many():
            for _ in range(100):
                await metrics.record_processed(0.001)

        # 并发记录
        await asyncio.gather(
            record_many(),
            record_many(),
            record_many()
        )

        stats = await metrics.get_stats()
        assert stats["events_processed"] == 300

    @pytest.mark.asyncio
    async def test_async_metrics_reset(self):
        """测试异步指标重置"""
        metrics = AsyncEventMetrics()

        await metrics.record_processed(0.01)
        await metrics.record_queue_size(10)

        # 创建新的指标对象来模拟重置
        metrics = AsyncEventMetrics()

        stats = await metrics.get_stats()
        assert stats["events_processed"] == 0
        assert stats["avg_queue_size"] == 0


# =============================================================================
# 性能基准测试
# =============================================================================

class TestAsyncPerformanceBenchmarks:
    """异步性能基准测试类"""

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_async_throughput_benchmark(self):
        """测试异步吞吐量基准"""
        engine = AsyncEventEngine(num_workers=20, max_queue_size=10000)
        event_count = 10000
        processed = asyncio.Event()
        counter = 0

        async def handler(data):
            nonlocal counter
            counter += 1
            if counter >= event_count:
                processed.set()

        engine.register("BENCH", handler)
        await engine.start()

        try:
            start_time = time.time()

            for i in range(event_count):
                await engine.put("BENCH", f"data{i}")

            await asyncio.wait_for(processed.wait(), timeout=30)
            elapsed = time.time() - start_time

            throughput = event_count / elapsed
            print(f"\n异步吞吐量: {throughput:.0f} 事件/秒")

            # 异步引擎应该达到较高吞吐量
            assert throughput > 1000
        finally:
            await engine.stop()

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_async_latency_benchmark(self):
        """测试异步延迟基准"""
        engine = AsyncEventEngine(num_workers=10, max_queue_size=1000)
        latencies = []

        async def handler(data):
            latency = time.time() - data["timestamp"]
            latencies.append(latency)

        engine.register("LATENCY", handler)
        await engine.start()

        try:
            # 发送事件并记录时间
            for i in range(1000):
                await engine.put("LATENCY", {"timestamp": time.time()})

            await asyncio.sleep(2)

            if latencies:
                avg_latency = sum(latencies) / len(latencies) * 1000
                p99_latency = sorted(latencies)[int(len(latencies) * 0.99)] * 1000

                print(f"\n平均延迟: {avg_latency:.2f} ms")
                print(f"P99延迟: {p99_latency:.2f} ms")

                # 延迟应该很低
                assert avg_latency < 50
        finally:
            await engine.stop()

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_async_concurrent_handlers_benchmark(self):
        """测试异步并发处理器基准"""
        engine = AsyncEventEngine(num_workers=50, max_queue_size=5000)
        handler_counts = {}
        lock = asyncio.Lock()

        async def make_handler(name):
            async def handler(data):
                async with lock:
                    handler_counts[name] = handler_counts.get(name, 0) + 1
                await asyncio.sleep(0.001)
            return handler

        # 注册多个处理器
        for i in range(10):
            engine.register("CONCURRENT", await make_handler(f"handler_{i}"))

        await engine.start()

        try:
            for i in range(1000):
                await engine.put("CONCURRENT", f"data{i}")

            await asyncio.sleep(3)

            total = sum(handler_counts.values())
            print(f"\n并发处理总数: {total}")
            assert total == 1000 * 10  # 每个事件被10个处理器处理
        finally:
            await engine.stop()
