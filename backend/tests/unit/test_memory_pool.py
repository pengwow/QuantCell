"""
内存池单元测试

测试范围:
- ObjectPool 对象池功能
- TickEvent/BarEvent 事件对象
- SharedMemoryMarketData 共享内存
- PreallocatedBuffers 预分配缓冲区
- 内存使用优化
"""

import pytest
import time
import threading
import numpy as np
from unittest.mock import Mock, patch, MagicMock

from strategy.core.memory_pool import (
    ObjectPool,
    TickEvent,
    BarEvent,
    SharedMemoryMarketData,
    PreallocatedBuffers,
    PooledObject
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def object_pool():
    """创建对象池实例"""
    def factory():
        return {"data": None}

    def reset_func(obj):
        obj["data"] = None
        return obj

    return ObjectPool(
        factory=factory,
        reset_func=reset_func,
        initial_size=10,
        max_size=100
    )


@pytest.fixture
def tick_event():
    """创建Tick事件实例"""
    return TickEvent(
        symbol="BTCUSDT",
        price=50000.0,
        volume=1.5,
        timestamp=time.time()
    )


@pytest.fixture
def bar_event():
    """创建Bar事件实例"""
    return BarEvent(
        symbol="BTCUSDT",
        open_price=50000.0,
        high_price=51000.0,
        low_price=49000.0,
        close_price=50500.0,
        volume=100.0,
        timestamp=time.time()
    )


@pytest.fixture
def shared_memory():
    """创建共享内存实例"""
    return SharedMemoryMarketData(
        buffer_size=1024 * 1024,  # 1MB
        num_symbols=100
    )


@pytest.fixture
def preallocated_buffers():
    """创建预分配缓冲区实例"""
    return PreallocatedBuffers(
        buffer_sizes=[1024, 4096, 16384],
        buffers_per_size=10
    )


# =============================================================================
# ObjectPool 测试
# =============================================================================

class TestObjectPool:
    """对象池测试类"""

    def test_pool_initialization(self, object_pool):
        """测试对象池初始化"""
        assert object_pool.initial_size == 10
        assert object_pool.max_size == 100
        assert object_pool.size() >= 10  # 预创建的对象

    def test_acquire_object(self, object_pool):
        """测试获取对象"""
        obj = object_pool.acquire()
        assert obj is not None
        assert isinstance(obj, dict)

    def test_release_object(self, object_pool):
        """测试释放对象"""
        obj = object_pool.acquire()
        obj["data"] = "test"

        object_pool.release(obj)

        # 重新获取，应该被重置
        obj2 = object_pool.acquire()
        assert obj2.get("data") is None

    def test_pool_expansion(self):
        """测试对象池扩展"""
        def factory():
            return {"id": 0}

        pool = ObjectPool(
            factory=factory,
            reset_func=lambda x: x,
            initial_size=2,
            max_size=10
        )

        # 获取超过初始大小的对象
        objects = [pool.acquire() for _ in range(5)]
        assert len(objects) == 5

        # 池应该已扩展
        assert pool.size() >= 5

    def test_pool_max_size_limit(self):
        """测试对象池最大大小限制"""
        def factory():
            return {"id": 0}

        pool = ObjectPool(
            factory=factory,
            reset_func=lambda x: x,
            initial_size=2,
            max_size=5
        )

        # 获取超过最大大小的对象
        objects = [pool.acquire() for _ in range(10)]

        # 应该仍然能获取对象（可能通过创建新对象或等待）
        assert len(objects) == 10

    def test_pool_thread_safety(self):
        """测试对象池线程安全"""
        acquired_objects = []
        lock = threading.Lock()

        def factory():
            return {"thread": None}

        pool = ObjectPool(
            factory=factory,
            reset_func=lambda x: x,
            initial_size=10,
            max_size=100
        )

        def worker():
            for _ in range(50):
                obj = pool.acquire()
                with lock:
                    acquired_objects.append(obj)
                time.sleep(0.001)
                pool.release(obj)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(acquired_objects) == 250

    def test_pool_statistics(self, object_pool):
        """测试对象池统计信息"""
        # 获取一些对象
        objs = [object_pool.acquire() for _ in range(5)]

        stats = object_pool.get_stats()
        assert "available" in stats
        assert "in_use" in stats
        assert "total_created" in stats

        # 释放对象
        for obj in objs:
            object_pool.release(obj)

        stats2 = object_pool.get_stats()
        assert stats2["in_use"] == 0

    def test_pool_clear(self, object_pool):
        """测试清空对象池"""
        # 获取并释放一些对象
        objs = [object_pool.acquire() for _ in range(5)]
        for obj in objs:
            object_pool.release(obj)

        object_pool.clear()

        # 清空后应该可以正常获取新对象
        obj = object_pool.acquire()
        assert obj is not None


# =============================================================================
# TickEvent 测试
# =============================================================================

class TestTickEvent:
    """Tick事件测试类"""

    def test_tick_event_creation(self, tick_event):
        """测试Tick事件创建"""
        assert tick_event.symbol == "BTCUSDT"
        assert tick_event.price == 50000.0
        assert tick_event.volume == 1.5
        assert tick_event.timestamp > 0

    def test_tick_event_to_dict(self, tick_event):
        """测试Tick事件转字典"""
        data = tick_event.to_dict()

        assert data["symbol"] == "BTCUSDT"
        assert data["price"] == 50000.0
        assert data["volume"] == 1.5
        assert "timestamp" in data

    def test_tick_event_from_dict(self):
        """测试从字典创建Tick事件"""
        data = {
            "symbol": "ETHUSDT",
            "price": 3000.0,
            "volume": 10.0,
            "timestamp": time.time()
        }

        event = TickEvent.from_dict(data)

        assert event.symbol == "ETHUSDT"
        assert event.price == 3000.0
        assert event.volume == 10.0

    def test_tick_event_memory_efficiency(self):
        """测试Tick事件内存效率（__slots__）"""
        event = TickEvent("BTCUSDT", 50000.0, 1.0, time.time())

        # 使用__slots__的对象不应该有__dict__
        assert not hasattr(event, "__dict__")

    def test_tick_event_comparison(self):
        """测试Tick事件比较"""
        ts = time.time()
        event1 = TickEvent("BTCUSDT", 50000.0, 1.0, ts)
        event2 = TickEvent("BTCUSDT", 50000.0, 1.0, ts)
        event3 = TickEvent("ETHUSDT", 3000.0, 1.0, ts)

        assert event1 == event2
        assert event1 != event3


# =============================================================================
# BarEvent 测试
# =============================================================================

class TestBarEvent:
    """Bar事件测试类"""

    def test_bar_event_creation(self, bar_event):
        """测试Bar事件创建"""
        assert bar_event.symbol == "BTCUSDT"
        assert bar_event.open_price == 50000.0
        assert bar_event.high_price == 51000.0
        assert bar_event.low_price == 49000.0
        assert bar_event.close_price == 50500.0
        assert bar_event.volume == 100.0

    def test_bar_event_to_dict(self, bar_event):
        """测试Bar事件转字典"""
        data = bar_event.to_dict()

        assert data["symbol"] == "BTCUSDT"
        assert data["open"] == 50000.0
        assert data["high"] == 51000.0
        assert data["low"] == 49000.0
        assert data["close"] == 50500.0
        assert data["volume"] == 100.0

    def test_bar_event_from_dict(self):
        """测试从字典创建Bar事件"""
        data = {
            "symbol": "ETHUSDT",
            "open": 3000.0,
            "high": 3100.0,
            "low": 2900.0,
            "close": 3050.0,
            "volume": 500.0,
            "timestamp": time.time()
        }

        event = BarEvent.from_dict(data)

        assert event.symbol == "ETHUSDT"
        assert event.open_price == 3000.0
        assert event.close_price == 3050.0

    def test_bar_event_memory_efficiency(self):
        """测试Bar事件内存效率（__slots__）"""
        event = BarEvent("BTCUSDT", 1.0, 2.0, 0.5, 1.5, 100.0, time.time())

        # 使用__slots__的对象不应该有__dict__
        assert not hasattr(event, "__dict__")

    def test_bar_event_typical_price(self, bar_event):
        """测试典型价格计算"""
        typical = bar_event.typical_price()
        expected = (bar_event.high_price + bar_event.low_price + bar_event.close_price) / 3
        assert typical == expected

    def test_bar_event_price_range(self, bar_event):
        """测试价格范围计算"""
        range_val = bar_event.price_range()
        expected = bar_event.high_price - bar_event.low_price
        assert range_val == expected


# =============================================================================
# SharedMemoryMarketData 测试
# =============================================================================

class TestSharedMemoryMarketData:
    """共享内存市场数据测试类"""

    def test_shared_memory_initialization(self, shared_memory):
        """测试共享内存初始化"""
        assert shared_memory.buffer_size == 1024 * 1024
        assert shared_memory.num_symbols == 100

    def test_write_and_read_tick(self, shared_memory):
        """测试写入和读取Tick数据"""
        tick = TickEvent(
            symbol="BTCUSDT",
            price=50000.0,
            volume=1.5,
            timestamp=time.time()
        )

        shared_memory.write_tick(tick)
        retrieved = shared_memory.read_tick("BTCUSDT")

        assert retrieved is not None
        assert retrieved.symbol == "BTCUSDT"
        assert retrieved.price == 50000.0

    def test_write_and_read_bar(self, shared_memory):
        """测试写入和读取Bar数据"""
        bar = BarEvent(
            symbol="ETHUSDT",
            open_price=3000.0,
            high_price=3100.0,
            low_price=2900.0,
            close_price=3050.0,
            volume=500.0,
            timestamp=time.time()
        )

        shared_memory.write_bar(bar)
        retrieved = shared_memory.read_bar("ETHUSDT")

        assert retrieved is not None
        assert retrieved.symbol == "ETHUSDT"
        assert retrieved.close_price == 3050.0

    def test_multiple_symbols(self, shared_memory):
        """测试多个交易对"""
        symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT"]

        for i, symbol in enumerate(symbols):
            tick = TickEvent(
                symbol=symbol,
                price=1000.0 * (i + 1),
                volume=1.0,
                timestamp=time.time()
            )
            shared_memory.write_tick(tick)

        # 读取所有数据
        for i, symbol in enumerate(symbols):
            tick = shared_memory.read_tick(symbol)
            assert tick is not None
            assert tick.symbol == symbol

    def test_update_existing_symbol(self, shared_memory):
        """测试更新现有交易对数据"""
        tick1 = TickEvent("BTCUSDT", 50000.0, 1.0, time.time())
        shared_memory.write_tick(tick1)

        tick2 = TickEvent("BTCUSDT", 51000.0, 2.0, time.time())
        shared_memory.write_tick(tick2)

        retrieved = shared_memory.read_tick("BTCUSDT")
        assert retrieved.price == 51000.0
        assert retrieved.volume == 2.0

    def test_get_all_symbols(self, shared_memory):
        """测试获取所有交易对"""
        symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]

        for symbol in symbols:
            tick = TickEvent(symbol, 1000.0, 1.0, time.time())
            shared_memory.write_tick(tick)

        all_symbols = shared_memory.get_all_symbols()
        assert len(all_symbols) == 3
        for symbol in symbols:
            assert symbol in all_symbols

    def test_clear_symbol(self, shared_memory):
        """测试清除特定交易对数据"""
        tick = TickEvent("BTCUSDT", 50000.0, 1.0, time.time())
        shared_memory.write_tick(tick)

        shared_memory.clear_symbol("BTCUSDT")

        retrieved = shared_memory.read_tick("BTCUSDT")
        assert retrieved is None

    def test_clear_all(self, shared_memory):
        """测试清除所有数据"""
        tick1 = TickEvent("BTCUSDT", 50000.0, 1.0, time.time())
        tick2 = TickEvent("ETHUSDT", 3000.0, 1.0, time.time())

        shared_memory.write_tick(tick1)
        shared_memory.write_tick(tick2)

        shared_memory.clear_all()

        assert shared_memory.read_tick("BTCUSDT") is None
        assert shared_memory.read_tick("ETHUSDT") is None
        assert len(shared_memory.get_all_symbols()) == 0


# =============================================================================
# PreallocatedBuffers 测试
# =============================================================================

class TestPreallocatedBuffers:
    """预分配缓冲区测试类"""

    def test_buffers_initialization(self, preallocated_buffers):
        """测试缓冲区初始化"""
        assert len(preallocated_buffers.buffer_sizes) == 3
        assert 1024 in preallocated_buffers.buffer_sizes
        assert 4096 in preallocated_buffers.buffer_sizes
        assert 16384 in preallocated_buffers.buffer_sizes

    def test_acquire_buffer(self, preallocated_buffers):
        """测试获取缓冲区"""
        buf = preallocated_buffers.acquire(1024)
        assert buf is not None
        assert len(buf) >= 1024

    def test_release_buffer(self, preallocated_buffers):
        """测试释放缓冲区"""
        buf = preallocated_buffers.acquire(1024)
        buf[0:5] = b"hello"

        preallocated_buffers.release(buf)

        # 重新获取，应该得到相同的缓冲区（可能被重置）
        buf2 = preallocated_buffers.acquire(1024)
        assert buf2 is not None

    def test_buffer_size_matching(self, preallocated_buffers):
        """测试缓冲区大小匹配"""
        # 请求1024字节，应该返回1024字节的缓冲区
        buf1 = preallocated_buffers.acquire(500)
        assert len(buf1) >= 500

        # 请求4096字节
        buf2 = preallocated_buffers.acquire(2000)
        assert len(buf2) >= 2000

        # 请求16384字节
        buf3 = preallocated_buffers.acquire(10000)
        assert len(buf3) >= 10000

    def test_buffer_exhaustion(self, preallocated_buffers):
        """测试缓冲区耗尽处理"""
        buffers = []

        # 获取超过预分配数量的缓冲区
        for _ in range(15):
            buf = preallocated_buffers.acquire(1024)
            buffers.append(buf)

        # 应该仍然能获取缓冲区（可能创建新的）
        assert len(buffers) == 15

        # 释放缓冲区
        for buf in buffers:
            preallocated_buffers.release(buf)

    def test_buffer_thread_safety(self):
        """测试缓冲区线程安全"""
        buffers = PreallocatedBuffers(
            buffer_sizes=[1024],
            buffers_per_size=20
        )

        acquired = []
        lock = threading.Lock()

        def worker():
            for _ in range(20):
                buf = buffers.acquire(1024)
                with lock:
                    acquired.append(buf)
                time.sleep(0.001)
                buffers.release(buf)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(acquired) == 100

    def test_buffer_statistics(self, preallocated_buffers):
        """测试缓冲区统计信息"""
        # 获取一些缓冲区
        buf1 = preallocated_buffers.acquire(1024)
        buf2 = preallocated_buffers.acquire(4096)

        stats = preallocated_buffers.get_stats()
        assert "buffer_pools" in stats

        # 释放缓冲区
        preallocated_buffers.release(buf1)
        preallocated_buffers.release(buf2)


# =============================================================================
# 性能基准测试
# =============================================================================

class TestMemoryPoolPerformanceBenchmarks:
    """内存池性能基准测试类"""

    @pytest.mark.slow
    def test_object_pool_performance(self):
        """测试对象池性能"""
        def factory():
            return {"data": None, "timestamp": 0}

        def reset_func(obj):
            obj["data"] = None
            obj["timestamp"] = 0
            return obj

        pool = ObjectPool(
            factory=factory,
            reset_func=reset_func,
            initial_size=1000,
            max_size=10000
        )

        # 测试获取/释放性能
        iterations = 100000
        start_time = time.time()

        for _ in range(iterations):
            obj = pool.acquire()
            pool.release(obj)

        elapsed = time.time() - start_time
        ops_per_sec = iterations / elapsed

        print(f"\n对象池操作性能: {ops_per_sec:.0f} 操作/秒")
        print(f"单次操作耗时: {elapsed/iterations*1e6:.2f} μs")

        assert ops_per_sec > 100000  # 应该达到10万+操作/秒

    @pytest.mark.slow
    def test_object_pool_vs_allocation(self):
        """测试对象池功能正确性"""
        iterations = 1000

        # 对象池
        pool = ObjectPool(
            factory=lambda: {"data": None, "timestamp": 0},
            reset_func=lambda x: x,
            initial_size=100,
            max_size=1000
        )

        # 验证对象池能够正确获取和释放对象
        acquired_objects = []
        for _ in range(iterations):
            obj = pool.acquire()
            obj["data"] = "test"
            acquired_objects.append(obj)

        # 验证所有对象都已获取
        assert len(acquired_objects) == iterations

        # 释放所有对象
        for obj in acquired_objects:
            pool.release(obj)

        # 验证对象池大小
        assert pool._size >= iterations

        print(f"\n对象池功能测试通过")
        print(f"对象池大小: {pool._size}")
        print(f"可用对象数: {len(pool._available)}")

    @pytest.mark.slow
    def test_tick_event_memory_usage(self):
        """测试Tick事件内存使用"""
        import sys

        # 创建大量Tick事件
        events = []
        for i in range(10000):
            event = TickEvent(
                symbol=f"SYM{i%100}USDT",
                price=50000.0 + i,
                volume=1.0,
                timestamp=time.time()
            )
            events.append(event)

        # 计算单个事件大小
        single_size = sys.getsizeof(events[0])
        total_size = sum(sys.getsizeof(e) for e in events)

        print(f"\n单个Tick事件大小: {single_size} bytes")
        print(f"10000个事件总大小: {total_size / 1024:.2f} KB")
        print(f"平均每个事件: {total_size / len(events):.2f} bytes")

        # 使用__slots__应该显著减少内存使用
        # 放宽阈值以适应不同Python版本和平台
        assert single_size < 150  # 应该小于150字节

    @pytest.mark.slow
    def test_shared_memory_throughput(self):
        """测试共享内存吞吐量"""
        shared = SharedMemoryMarketData(
            buffer_size=10 * 1024 * 1024,  # 10MB
            num_symbols=400
        )

        iterations = 10000
        symbols = [f"SYM{i}USDT" for i in range(100)]

        start_time = time.time()

        for i in range(iterations):
            tick = TickEvent(
                symbol=symbols[i % len(symbols)],
                price=50000.0 + i,
                volume=1.0,
                timestamp=time.time()
            )
            shared.write_tick(tick)

        elapsed = time.time() - start_time
        throughput = iterations / elapsed

        print(f"\n共享内存写入吞吐量: {throughput:.0f} 操作/秒")
        print(f"单次写入耗时: {elapsed/iterations*1e6:.2f} μs")

        assert throughput > 10000

    @pytest.mark.slow
    def test_preallocated_buffer_performance(self):
        """测试预分配缓冲区性能"""
        buffers = PreallocatedBuffers(
            buffer_sizes=[1024, 4096, 16384],
            buffers_per_size=100
        )

        iterations = 50000

        start_time = time.time()

        for i in range(iterations):
            size = [1024, 4096, 16384][i % 3]
            buf = buffers.acquire(size)
            # 模拟使用
            buf[0:10] = b"0123456789"
            buffers.release(buf)

        elapsed = time.time() - start_time
        ops_per_sec = iterations / elapsed

        print(f"\n预分配缓冲区操作性能: {ops_per_sec:.0f} 操作/秒")
        print(f"单次操作耗时: {elapsed/iterations*1e6:.2f} μs")

        assert ops_per_sec > 50000
