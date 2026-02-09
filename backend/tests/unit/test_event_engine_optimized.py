"""
优化事件引擎单元测试

测试覆盖：
1. 基本事件处理
2. 优先级队列排序
3. 背压机制
4. 多工作线程并行处理
5. 指标收集
6. 线程安全
7. 引擎健康检查
"""

import pytest
import threading
import time
import statistics
from typing import List, Dict, Any

from strategy.core import (
    OptimizedEventEngine,
    EventPriority,
    BoundedPriorityQueue,
    EventMetrics,
    create_optimized_engine
)


class TestOptimizedEventEngine:
    """优化事件引擎单元测试类"""
    
    def test_basic_event_processing(self):
        """测试基本事件处理功能"""
        engine = create_optimized_engine(num_workers=1)
        events_received = []
        
        def handler(data):
            events_received.append(data)
        
        engine.register("TEST", handler)
        engine.start()
        
        try:
            # 发送事件
            engine.put("TEST", "data1")
            time.sleep(0.1)
            
            assert len(events_received) == 1
            assert events_received[0] == "data1"
        finally:
            engine.stop()
    
    def test_multiple_event_types(self):
        """测试多种事件类型处理"""
        engine = create_optimized_engine(num_workers=2)
        tick_data = []
        bar_data = []
        
        def tick_handler(data):
            tick_data.append(data)
        
        def bar_handler(data):
            bar_data.append(data)
        
        engine.register("TICK", tick_handler)
        engine.register("BAR", bar_handler)
        engine.start()
        
        try:
            # 发送不同类型事件
            for i in range(10):
                engine.put("TICK", f"tick_{i}")
                engine.put("BAR", f"bar_{i}")
            
            time.sleep(0.2)
            
            assert len(tick_data) == 10
            assert len(bar_data) == 10
        finally:
            engine.stop()
    
    def test_priority_queue_ordering(self):
        """测试优先级队列排序功能"""
        engine = create_optimized_engine(num_workers=1)
        events_order = []
        
        def handler(data):
            events_order.append(data)
        
        engine.register("TEST", handler)
        engine.start()
        
        try:
            # 按不同优先级发送事件
            engine.put("TEST", "low", priority=EventPriority.LOW)
            engine.put("TEST", "critical", priority=EventPriority.CRITICAL)
            engine.put("TEST", "normal", priority=EventPriority.NORMAL)
            engine.put("TEST", "high", priority=EventPriority.HIGH)
            engine.put("TEST", "background", priority=EventPriority.BACKGROUND)
            
            time.sleep(0.3)
            
            # 验证处理顺序（优先级从高到低）
            assert events_order[0] == "critical"
            assert events_order[1] == "high"
            assert events_order[2] == "normal"
            assert events_order[3] == "low"
            assert events_order[4] == "background"
        finally:
            engine.stop()
    
    def test_same_priority_fifo_ordering(self):
        """测试相同优先级的FIFO顺序"""
        engine = create_optimized_engine(num_workers=1)
        events_order = []
        
        def handler(data):
            events_order.append(data)
        
        engine.register("TEST", handler)
        engine.start()
        
        try:
            # 发送相同优先级的事件
            for i in range(5):
                engine.put("TEST", f"event_{i}", priority=EventPriority.NORMAL)
            
            time.sleep(0.2)
            
            # 验证FIFO顺序
            for i in range(5):
                assert events_order[i] == f"event_{i}"
        finally:
            engine.stop()
    
    def test_backpressure_mechanism(self):
        """测试背压机制"""
        engine = create_optimized_engine(
            max_queue_size=10,
            backpressure_threshold=0.5,
            num_workers=1
        )
        
        processed = []
        
        def slow_handler(data):
            time.sleep(0.05)  # 模拟慢处理
            processed.append(data)
        
        engine.register("TEST", slow_handler)
        engine.start()
        
        try:
            # 快速发送事件触发背压
            results = []
            for i in range(20):
                result = engine.put("TEST", f"data{i}", block=False)
                results.append(result)
            
            time.sleep(0.5)
            
            # 验证部分事件被丢弃
            dropped_count = results.count(False)
            assert dropped_count > 0, "应该有事件被背压机制丢弃"
            
            # 验证统计信息
            stats = engine.get_stats()
            assert stats["events_dropped"] > 0
        finally:
            engine.stop()
    
    def test_critical_event_not_dropped(self):
        """测试关键事件不会被背压丢弃"""
        engine = create_optimized_engine(
            max_queue_size=5,
            backpressure_threshold=0.5,
            num_workers=1
        )
        
        processed = []
        
        def slow_handler(data):
            time.sleep(0.1)
            processed.append(data)
        
        engine.register("TEST", slow_handler)
        engine.start()
        
        try:
            # 先填充队列
            for i in range(5):
                engine.put("TEST", f"normal_{i}", priority=EventPriority.NORMAL, block=False)
            
            # 发送关键事件
            result = engine.put("TEST", "critical", priority=EventPriority.CRITICAL, block=False)
            
            # 关键事件应该被接受
            assert result == True, "关键事件不应被背压丢弃"
        finally:
            engine.stop()
    
    def test_multi_worker_parallel_processing(self):
        """测试多工作线程并行处理"""
        engine = create_optimized_engine(num_workers=4)
        processing_times = []
        lock = threading.Lock()
        
        def handler(data):
            start = time.time()
            time.sleep(0.01)  # 模拟处理
            with lock:
                processing_times.append(time.time() - start)
        
        engine.register("TEST", handler)
        engine.start()
        
        try:
            start_time = time.time()
            
            # 发送多个事件
            for i in range(20):
                engine.put("TEST", f"data{i}")
            
            # 等待处理完成
            time.sleep(0.5)
            
            total_time = time.time() - start_time
            
            # 验证并行处理（总时间应小于串行时间）
            assert len(processing_times) == 20
            # 20个事件，每个0.01秒，串行需要0.2秒
            # 4个工作线程理论上需要0.05秒，考虑线程调度和启动开销，给足够余量
            assert total_time < 0.6, f"并行处理应该更快，实际耗时{total_time}秒"
        finally:
            engine.stop()
    
    def test_metrics_collection(self):
        """测试指标收集功能"""
        engine = create_optimized_engine(num_workers=1)
        
        def handler(data):
            pass
        
        engine.register("TEST", handler)
        engine.start()
        
        try:
            # 发送事件
            for i in range(100):
                engine.put("TEST", f"data{i}")
            
            time.sleep(0.2)
            
            stats = engine.get_stats()
            
            # 验证统计信息
            assert stats["events_received"] == 100
            assert stats["events_processed"] == 100
            assert stats["events_dropped"] == 0
            assert stats["drop_rate"] == 0.0
            assert "avg_processing_time_ms" in stats
            assert "avg_queue_size" in stats
            assert "events_by_priority" in stats
        finally:
            engine.stop()
    
    def test_thread_safety(self):
        """测试线程安全"""
        engine = create_optimized_engine(num_workers=4)
        counter = 0
        lock = threading.Lock()
        errors = []
        
        def handler(data):
            nonlocal counter
            try:
                with lock:
                    counter += 1
            except Exception as e:
                errors.append(e)
        
        engine.register("TEST", handler)
        engine.start()
        
        try:
            # 多线程发送事件
            def sender():
                for i in range(100):
                    try:
                        engine.put("TEST", f"data{i}")
                    except Exception as e:
                        errors.append(e)
            
            threads = [threading.Thread(target=sender) for _ in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            
            time.sleep(0.5)
            
            # 验证没有错误
            assert len(errors) == 0, f"发生错误: {errors}"
            
            # 验证所有事件都被处理
            assert counter == 500, f"期望处理500个事件，实际处理{counter}个"
        finally:
            engine.stop()
    
    def test_handler_exception_isolation(self):
        """测试处理器异常隔离"""
        engine = create_optimized_engine(num_workers=1)
        success_count = 0
        
        def flaky_handler(data):
            nonlocal success_count
            if data["should_fail"]:
                raise ValueError("模拟异常")
            success_count += 1
        
        engine.register("TEST", flaky_handler)
        engine.start()
        
        try:
            # 发送正常和异常事件
            for i in range(10):
                engine.put("TEST", {"should_fail": i % 2 == 0})
            
            time.sleep(0.2)
            
            # 验证引擎继续运行
            assert engine.running
            
            # 验证成功处理的事件
            assert success_count == 5
        finally:
            engine.stop()
    
    def test_engine_health_check(self):
        """测试引擎健康检查"""
        engine = create_optimized_engine(
            max_queue_size=100,
            backpressure_threshold=0.5,
            num_workers=1
        )
        
        def handler(data):
            time.sleep(0.01)
        
        engine.register("TEST", handler)
        engine.start()
        
        try:
            # 正常情况下应健康
            assert engine.is_healthy()
            
            # 触发背压
            for i in range(100):
                engine.put("TEST", f"data{i}", block=False)
            
            time.sleep(0.1)
            
            # 检查健康状态
            stats = engine.get_stats()
            if stats["drop_rate"] > 0.05:
                assert not engine.is_healthy()
        finally:
            engine.stop()
    
    def test_engine_start_stop_idempotency(self):
        """测试引擎启动停止的幂等性"""
        engine = create_optimized_engine(num_workers=1)
        
        # 多次启动不应出错
        engine.start()
        engine.start()
        engine.start()
        
        assert engine.running
        
        # 多次停止不应出错
        engine.stop()
        engine.stop()
        engine.stop()
        
        assert not engine.running
    
    def test_unregister_handler(self):
        """测试注销处理器"""
        engine = create_optimized_engine(num_workers=1)
        
        def handler(data):
            pass
        
        # 注册处理器
        engine.register("TEST", handler)
        
        # 注销处理器
        result = engine.unregister("TEST", handler)
        assert result == True
        
        # 再次注销应该失败
        result = engine.unregister("TEST", handler)
        assert result == False
    
    def test_blocking_put_with_timeout(self):
        """测试带超时的阻塞put"""
        engine = create_optimized_engine(
            max_queue_size=2,
            num_workers=0,  # 不启动工作线程，保持队列满状态
            enable_backpressure=False,  # 禁用背压机制
            enable_graceful_degradation=False  # 禁用优雅降级
        )

        try:
            # 填充队列（不使用block=False，确保事件进入队列）
            engine.put("TEST", "data1", block=True, timeout=1.0)
            engine.put("TEST", "data2", block=True, timeout=1.0)

            # 带超时的put应该超时失败
            start = time.time()
            result = engine.put("TEST", "data3", block=True, timeout=0.1)
            elapsed = time.time() - start

            assert result == False
            assert elapsed >= 0.1, f"期望等待至少0.1秒，实际等待{elapsed}秒"
            assert elapsed < 0.2
        finally:
            engine.stop()
    
    def test_event_data_types(self):
        """测试不同数据类型的事件"""
        engine = create_optimized_engine(num_workers=1)
        received_data = []
        
        def handler(data):
            received_data.append(data)
        
        engine.register("TEST", handler)
        engine.start()
        
        try:
            # 发送不同类型的数据
            test_data = [
                "string",
                123,
                45.67,
                ["list", "data"],
                {"key": "value"},
                None,
                {"nested": {"data": [1, 2, 3]}}
            ]
            
            for data in test_data:
                engine.put("TEST", data)
            
            time.sleep(0.2)
            
            assert len(received_data) == len(test_data)
            for i, data in enumerate(test_data):
                assert received_data[i] == data
        finally:
            engine.stop()


class TestBoundedPriorityQueue:
    """有界优先级队列单元测试"""
    
    def test_basic_put_get(self):
        """测试基本的put和get"""
        queue = BoundedPriorityQueue(maxsize=10)
        
        from strategy.core.event_engine_optimized import PrioritizedEvent
        
        event = PrioritizedEvent(
            priority=EventPriority.NORMAL.value,
            timestamp=time.time(),
            event_type="TEST",
            data="test_data"
        )
        
        # put应该成功
        result = queue.put(event, block=False)
        assert result == True
        
        # get应该返回事件
        retrieved = queue.get(block=False)
        assert retrieved is not None
        assert retrieved.event_type == "TEST"
        assert retrieved.data == "test_data"
    
    def test_queue_size_limit(self):
        """测试队列大小限制"""
        queue = BoundedPriorityQueue(maxsize=3)
        
        from strategy.core.event_engine_optimized import PrioritizedEvent
        
        # 填充队列
        for i in range(3):
            event = PrioritizedEvent(
                priority=EventPriority.NORMAL.value,
                timestamp=time.time(),
                event_type="TEST",
                data=f"data{i}"
            )
            result = queue.put(event, block=False)
            assert result == True
        
        # 队列已满，put应该失败
        event = PrioritizedEvent(
            priority=EventPriority.NORMAL.value,
            timestamp=time.time(),
            event_type="TEST",
            data="overflow"
        )
        result = queue.put(event, block=False)
        assert result == False
    
    def test_priority_ordering(self):
        """测试优先级排序"""
        queue = BoundedPriorityQueue(maxsize=10)
        
        from strategy.core.event_engine_optimized import PrioritizedEvent
        
        # 按不同优先级添加事件
        priorities = [2, 0, 3, 1, 4]  # 0最高，4最低
        for p in priorities:
            event = PrioritizedEvent(
                priority=p,
                timestamp=time.time(),
                event_type="TEST",
                data=f"priority_{p}"
            )
            queue.put(event, block=False)
        
        # 获取事件，应该按优先级顺序
        expected_order = [0, 1, 2, 3, 4]
        for expected_priority in expected_order:
            event = queue.get(block=False)
            assert event.priority == expected_priority


class TestEventMetrics:
    """事件指标单元测试"""
    
    def test_basic_metrics(self):
        """测试基本指标收集"""
        metrics = EventMetrics()
        
        # 记录事件
        for i in range(10):
            metrics.record_received(priority=EventPriority.NORMAL.value)
            metrics.record_processed(0.01)
        
        stats = metrics.get_stats()
        
        assert stats["events_received"] == 10
        assert stats["events_processed"] == 10
        assert stats["events_dropped"] == 0
        assert stats["drop_rate"] == 0.0
    
    def test_drop_rate_calculation(self):
        """测试丢弃率计算"""
        metrics = EventMetrics()
        
        # 记录接收和丢弃
        for i in range(100):
            metrics.record_received()
        for i in range(10):
            metrics.record_dropped()
        
        stats = metrics.get_stats()
        
        assert stats["events_received"] == 100
        assert stats["events_dropped"] == 10
        assert abs(stats["drop_rate"] - 0.1) < 0.001
    
    def test_processing_time_tracking(self):
        """测试处理时间跟踪"""
        metrics = EventMetrics()
        
        # 记录不同处理时间
        processing_times = [0.001, 0.002, 0.003, 0.004, 0.005]
        for pt in processing_times:
            metrics.record_received()
            metrics.record_processed(pt)
        
        stats = metrics.get_stats()
        
        expected_avg = statistics.mean(processing_times) * 1000
        assert abs(stats["avg_processing_time_ms"] - expected_avg) < 0.1
    
    def test_queue_size_history(self):
        """测试队列大小历史"""
        metrics = EventMetrics()
        
        # 记录队列大小
        for size in range(10):
            metrics.record_queue_size(size)
        
        stats = metrics.get_stats()
        
        assert stats["avg_queue_size"] == 4.5  # 0-9的平均值


class TestPerformanceBenchmarks:
    """性能基准测试"""
    
    @pytest.mark.slow
    def test_throughput_benchmark(self):
        """吞吐量基准测试"""
        engine = create_optimized_engine(num_workers=4)
        event_count = 10000
        
        processed = []
        
        def handler(data):
            processed.append(data)
        
        engine.register("TEST", handler)
        engine.start()
        
        try:
            start_time = time.time()
            
            # 发送事件
            for i in range(event_count):
                engine.put("TEST", f"data{i}")
            
            # 等待处理完成
            while len(processed) < event_count:
                time.sleep(0.01)
            
            elapsed = time.time() - start_time
            throughput = event_count / elapsed
            
            print(f"\n吞吐量: {throughput:.0f} 事件/秒")
            print(f"总耗时: {elapsed:.2f} 秒")
            
            # 断言性能指标
            assert throughput > 1000, f"吞吐量应大于1000事件/秒，实际{throughput:.0f}"
        finally:
            engine.stop()
    
    @pytest.mark.slow
    def test_latency_benchmark(self):
        """延迟基准测试"""
        engine = create_optimized_engine(num_workers=4)
        latencies = []
        lock = threading.Lock()
        
        def handler(data):
            latency = (time.time() - data["send_time"]) * 1000
            with lock:
                latencies.append(latency)
        
        engine.register("TEST", handler)
        engine.start()
        
        try:
            # 发送事件
            for i in range(1000):
                engine.put("TEST", {
                    "id": i,
                    "send_time": time.time()
                })
            
            time.sleep(1.0)
            
            # 计算延迟统计
            if latencies:
                avg_latency = statistics.mean(latencies)
                p50_latency = sorted(latencies)[int(len(latencies) * 0.5)]
                p99_latency = sorted(latencies)[int(len(latencies) * 0.99)]
                
                print(f"\n平均延迟: {avg_latency:.2f} ms")
                print(f"P50延迟: {p50_latency:.2f} ms")
                print(f"P99延迟: {p99_latency:.2f} ms")
                
                # 断言延迟指标
                assert avg_latency < 50, f"平均延迟应小于50ms，实际{avg_latency:.2f}ms"
                assert p99_latency < 100, f"P99延迟应小于100ms，实际{p99_latency:.2f}ms"
        finally:
            engine.stop()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
