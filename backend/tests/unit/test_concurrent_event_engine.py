"""
并发事件引擎单元测试

测试范围:
- ConcurrentEventEngine 基本功能
- 分片路由
- 并发处理
- 负载均衡
- 性能指标收集
"""

import pytest
import time
import threading
from unittest.mock import Mock, patch

from strategy.core.concurrent_event_engine import (
    ConcurrentEventEngine,
    SymbolShard,
    SymbolEvent,
    ShardRouter
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def concurrent_engine():
    """创建并发事件引擎实例"""
    engine = ConcurrentEventEngine(num_shards=4, max_queue_size_per_shard=1000)
    yield engine
    # 清理
    if engine.running:
        engine.stop()


@pytest.fixture
def running_concurrent_engine():
    """创建并启动的并发事件引擎"""
    engine = ConcurrentEventEngine(num_shards=4, max_queue_size_per_shard=1000)
    engine.start()
    yield engine
    engine.stop()


@pytest.fixture
def symbol_shard():
    """创建交易对分片实例"""
    return SymbolShard(shard_id=0, max_queue_size=100)


@pytest.fixture
def shard_router():
    """创建分片路由器实例"""
    return ShardRouter(num_shards=4)


# =============================================================================
# ConcurrentEventEngine 测试
# =============================================================================

class TestConcurrentEventEngine:
    """并发事件引擎测试类"""

    def test_basic_concurrent_event_processing(self, concurrent_engine):
        """测试基本并发事件处理"""
        events_received = []

        def handler(data):
            events_received.append(data)

        concurrent_engine.register("TEST", handler)
        concurrent_engine.start()

        try:
            concurrent_engine.put("TEST", "data1", symbol="BTCUSDT")
            time.sleep(0.1)
            assert len(events_received) == 1
            assert events_received[0] == "data1"
        finally:
            concurrent_engine.stop()

    def test_symbol_based_routing(self, concurrent_engine):
        """测试基于交易对的路由"""
        results = {}

        def handler(data):
            symbol = data.get("symbol", "unknown")
            results[symbol] = results.get(symbol, 0) + 1

        concurrent_engine.register("TICK", handler)
        concurrent_engine.start()

        try:
            # 发送不同交易对的事件
            for i in range(10):
                concurrent_engine.put("TICK", {"symbol": "BTCUSDT", "price": i}, symbol="BTCUSDT")
                concurrent_engine.put("TICK", {"symbol": "ETHUSDT", "price": i}, symbol="ETHUSDT")

            time.sleep(0.5)

            assert results.get("BTCUSDT") == 10
            assert results.get("ETHUSDT") == 10
        finally:
            concurrent_engine.stop()

    def test_same_symbol_same_shard(self, concurrent_engine):
        """测试相同交易对路由到相同分片"""
        shard_assignments = []

        # 通过内部方法获取分片分配
        for i in range(10):
            shard_id = concurrent_engine._get_shard_id("BTCUSDT")
            shard_assignments.append(shard_id)

        # 所有相同交易对应该分配到同一个分片
        assert len(set(shard_assignments)) == 1

    def test_concurrent_processing(self, concurrent_engine):
        """测试并发处理"""
        processed_count = 0
        lock = threading.Lock()

        def handler(data):
            nonlocal processed_count
            time.sleep(0.01)  # 模拟处理时间
            with lock:
                processed_count += 1

        concurrent_engine.register("TEST", handler)
        concurrent_engine.start()

        try:
            start_time = time.time()

            # 发送多个事件到不同交易对
            for i in range(100):
                symbol = f"SYM{i % 10}USDT"
                concurrent_engine.put("TEST", f"data{i}", symbol=symbol)

            time.sleep(2)
            elapsed = time.time() - start_time

            assert processed_count == 100
            # 并发处理应该比串行快
            assert elapsed < 1.5  # 串行需要1秒，并发应该更快
        finally:
            concurrent_engine.stop()

    def test_shard_isolation(self, concurrent_engine):
        """测试分片隔离"""
        results = {"shard_0": 0, "shard_1": 0, "shard_2": 0, "shard_3": 0}

        def handler(data):
            shard_id = data.get("shard_id")
            results[f"shard_{shard_id}"] += 1

        concurrent_engine.register("TEST", handler)
        concurrent_engine.start()

        try:
            # 发送事件到不同交易对
            symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "XRPUSDT", "DOTUSDT", "UNIUSDT", "LINKUSDT"]
            for i in range(80):
                symbol = symbols[i % len(symbols)]
                shard_id = concurrent_engine._get_shard_id(symbol)
                concurrent_engine.put("TEST", {"shard_id": shard_id}, symbol=symbol)

            time.sleep(0.5)

            # 验证事件被分发到不同分片
            total = sum(results.values())
            assert total == 80
        finally:
            concurrent_engine.stop()

    def test_metrics_collection(self, concurrent_engine):
        """测试指标收集"""
        def handler(data):
            time.sleep(0.01)

        concurrent_engine.register("TEST", handler)
        concurrent_engine.start()

        try:
            for i in range(20):
                concurrent_engine.put("TEST", f"data{i}", symbol=f"SYM{i}USDT")

            time.sleep(0.5)

            metrics = concurrent_engine.get_metrics()
            assert metrics["total_processed"] >= 20
            assert "shard_metrics" in metrics
            assert len(metrics["shard_metrics"]) == 4
        finally:
            concurrent_engine.stop()

    def test_handler_exception_isolation(self, concurrent_engine):
        """测试处理器异常隔离"""
        results = []

        def failing_handler(data):
            raise ValueError("测试异常")

        def good_handler(data):
            results.append(data)

        concurrent_engine.register("FAIL", failing_handler)
        concurrent_engine.register("GOOD", good_handler)
        concurrent_engine.start()

        try:
            concurrent_engine.put("FAIL", "bad_data", symbol="BTCUSDT")
            concurrent_engine.put("GOOD", "good_data", symbol="ETHUSDT")
            time.sleep(0.2)

            assert len(results) == 1
            assert results[0] == "good_data"
        finally:
            concurrent_engine.stop()

    def test_engine_lifecycle(self, concurrent_engine):
        """测试引擎生命周期管理"""
        assert not concurrent_engine.running

        concurrent_engine.start()
        assert concurrent_engine.running

        concurrent_engine.stop()
        assert not concurrent_engine.running

    def test_double_start_stop(self, concurrent_engine):
        """测试重复启动和停止"""
        concurrent_engine.start()
        concurrent_engine.start()  # 应该安全
        assert concurrent_engine.running

        concurrent_engine.stop()
        concurrent_engine.stop()  # 应该安全
        assert not concurrent_engine.running

    def test_unregister_handler(self, concurrent_engine):
        """测试注销处理器"""
        results = []

        def handler(data):
            results.append(data)

        concurrent_engine.register("TEST", handler)
        concurrent_engine.start()

        try:
            concurrent_engine.put("TEST", "data1", symbol="BTCUSDT")
            time.sleep(0.1)

            concurrent_engine.unregister("TEST", handler)
            concurrent_engine.put("TEST", "data2", symbol="BTCUSDT")
            time.sleep(0.1)

            assert len(results) == 1
        finally:
            concurrent_engine.stop()

    def test_clear_handlers(self, concurrent_engine):
        """测试清空处理器"""
        results = []

        def handler(data):
            results.append(data)

        concurrent_engine.register("TEST", handler)
        concurrent_engine.start()

        try:
            concurrent_engine.put("TEST", "data1", symbol="BTCUSDT")
            time.sleep(0.1)

            concurrent_engine.clear_handlers("TEST")
            concurrent_engine.put("TEST", "data2", symbol="BTCUSDT")
            time.sleep(0.1)

            assert len(results) == 1
        finally:
            concurrent_engine.stop()

    def test_get_all_handlers(self, concurrent_engine):
        """测试获取所有处理器"""
        def handler1(data):
            pass

        def handler2(data):
            pass

        concurrent_engine.register("TEST1", handler1)
        concurrent_engine.register("TEST2", handler2)

        handlers = concurrent_engine.get_all_handlers()
        assert "TEST1" in handlers
        assert "TEST2" in handlers
        assert len(handlers["TEST1"]) == 1
        assert len(handlers["TEST2"]) == 1

    def test_put_without_symbol(self, concurrent_engine):
        """测试不带交易对的事件放入"""
        results = []

        def handler(data):
            results.append(data)

        concurrent_engine.register("TEST", handler)
        concurrent_engine.start()

        try:
            # 不带symbol应该使用默认分片
            concurrent_engine.put("TEST", "data1")
            time.sleep(0.1)

            assert len(results) == 1
        finally:
            concurrent_engine.stop()

    def test_queue_size_per_shard(self):
        """测试每个分片的队列大小限制"""
        engine = ConcurrentEventEngine(num_shards=2, max_queue_size_per_shard=5)

        def slow_handler(data):
            time.sleep(1)

        engine.register("TEST", slow_handler)
        engine.start()

        try:
            # 填满一个分片的队列
            for i in range(10):
                engine.put("TEST", f"data{i}", symbol="BTCUSDT")

            time.sleep(0.1)

            # 获取指标，检查队列大小
            metrics = engine.get_metrics()
            # 队列应该有背压机制
            assert "total_queued" in metrics
        finally:
            engine.stop()


# =============================================================================
# SymbolShard 测试
# =============================================================================

class TestSymbolShard:
    """交易对分片测试类"""

    def test_shard_initialization(self, symbol_shard):
        """测试分片初始化"""
        assert symbol_shard.shard_id == 0
        assert symbol_shard.max_queue_size == 100
        assert not symbol_shard.running

    def test_shard_start_stop(self, symbol_shard):
        """测试分片启动和停止"""
        assert not symbol_shard.running

        symbol_shard.start()
        assert symbol_shard.running

        symbol_shard.stop()
        assert not symbol_shard.running

    def test_shard_put_event(self, symbol_shard):
        """测试分片放入事件"""
        results = []

        def handler(event):
            results.append(event.data)

        symbol_shard.register("TEST", handler)
        symbol_shard.start()

        try:
            event = SymbolEvent(event_type="TEST", data="test_data", symbol="BTCUSDT")
            symbol_shard.put(event)
            time.sleep(0.1)

            assert len(results) == 1
            assert results[0] == "test_data"
        finally:
            symbol_shard.stop()

    def test_shard_queue_size(self, symbol_shard):
        """测试分片队列大小"""
        assert symbol_shard.qsize() == 0

        event = SymbolEvent(event_type="TEST", data="test", symbol="BTCUSDT")
        symbol_shard.put(event, block=False)

        # 未启动时分片不会处理事件
        assert symbol_shard.qsize() == 1


# =============================================================================
# ShardRouter 测试
# =============================================================================

class TestShardRouter:
    """分片路由器测试类"""

    def test_router_initialization(self, shard_router):
        """测试路由器初始化"""
        assert shard_router.num_shards == 4

    def test_consistent_hashing(self, shard_router):
        """测试一致性哈希"""
        # 相同交易对应该总是路由到相同分片
        shard1 = shard_router.get_shard("BTCUSDT")
        shard2 = shard_router.get_shard("BTCUSDT")
        shard3 = shard_router.get_shard("BTCUSDT")

        assert shard1 == shard2 == shard3

    def test_different_symbols_different_shards(self, shard_router):
        """测试不同交易对可能路由到不同分片"""
        shards = set()
        symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "XRPUSDT", "DOTUSDT", "UNIUSDT", "LINKUSDT"]

        for symbol in symbols:
            shard = shard_router.get_shard(symbol)
            shards.add(shard)

        # 应该有多个分片被使用
        assert len(shards) > 1

    def test_shard_distribution_balance(self, shard_router):
        """测试分片分布均衡性"""
        shard_counts = {i: 0 for i in range(shard_router.num_shards)}

        # 模拟100个交易对
        for i in range(100):
            symbol = f"SYM{i}USDT"
            shard = shard_router.get_shard(symbol)
            shard_counts[shard] += 1

        # 检查分布是否相对均衡（没有分片为空）
        for count in shard_counts.values():
            assert count > 0, "某些分片没有被使用"

    def test_empty_symbol(self, shard_router):
        """测试空交易对处理"""
        shard = shard_router.get_shard("")
        assert 0 <= shard < shard_router.num_shards

    def test_none_symbol(self, shard_router):
        """测试None交易对处理"""
        shard = shard_router.get_shard(None)
        assert 0 <= shard < shard_router.num_shards


# =============================================================================
# SymbolEvent 测试
# =============================================================================

class TestSymbolEvent:
    """交易对事件测试类"""

    def test_event_creation(self):
        """测试事件创建"""
        event = SymbolEvent(
            event_type="TICK",
            data={"price": 50000},
            symbol="BTCUSDT",
            priority=1
        )

        assert event.event_type == "TICK"
        assert event.data == {"price": 50000}
        assert event.symbol == "BTCUSDT"
        assert event.priority == 1
        assert event.timestamp > 0

    def test_event_default_priority(self):
        """测试事件默认优先级"""
        event = SymbolEvent(
            event_type="TICK",
            data={"price": 50000},
            symbol="BTCUSDT"
        )

        assert event.priority == 0

    def test_event_comparison(self):
        """测试事件比较（用于优先级队列）"""
        event_high = SymbolEvent(
            event_type="TICK",
            data={},
            symbol="BTCUSDT",
            priority=1
        )
        event_low = SymbolEvent(
            event_type="TICK",
            data={},
            symbol="ETHUSDT",
            priority=0
        )

        # 高优先级应该"小于"低优先级（在最小堆中先出）
        assert event_high < event_low


# =============================================================================
# 性能基准测试
# =============================================================================

class TestConcurrentPerformanceBenchmarks:
    """并发性能基准测试类"""

    @pytest.mark.slow
    def test_concurrent_throughput_benchmark(self):
        """测试并发吞吐量基准"""
        engine = ConcurrentEventEngine(num_shards=8, max_queue_size_per_shard=10000)
        event_count = 10000
        processed = 0
        lock = threading.Lock()

        def handler(data):
            nonlocal processed
            with lock:
                processed += 1

        engine.register("BENCH", handler)
        engine.start()

        try:
            start_time = time.time()

            # 发送事件到不同交易对
            for i in range(event_count):
                symbol = f"SYM{i % 100}USDT"
                engine.put("BENCH", f"data{i}", symbol=symbol)

            # 等待处理完成
            timeout = 30
            elapsed = 0
            while processed < event_count and elapsed < timeout:
                time.sleep(0.1)
                elapsed = time.time() - start_time

            total_time = time.time() - start_time
            throughput = processed / total_time

            print(f"\n并发吞吐量: {throughput:.0f} 事件/秒")
            print(f"处理事件数: {processed}/{event_count}")

            # 并发引擎应该达到较高吞吐量
            assert throughput > 5000
            assert processed == event_count
        finally:
            engine.stop()

    @pytest.mark.slow
    def test_shard_load_balance_benchmark(self):
        """测试分片负载均衡基准"""
        engine = ConcurrentEventEngine(num_shards=8, max_queue_size_per_shard=10000)
        shard_counts = {i: 0 for i in range(8)}
        lock = threading.Lock()

        def handler(data):
            shard_id = data.get("shard_id", 0)
            with lock:
                shard_counts[shard_id] += 1

        engine.register("BENCH", handler)
        engine.start()

        try:
            # 发送事件
            for i in range(8000):
                symbol = f"SYM{i % 200}USDT"
                shard_id = engine._get_shard_id(symbol)
                engine.put("BENCH", {"shard_id": shard_id}, symbol=symbol)

            time.sleep(3)

            # 检查负载均衡
            print(f"\n分片负载分布: {shard_counts}")

            counts = list(shard_counts.values())
            avg_count = sum(counts) / len(counts)
            max_deviation = max(abs(c - avg_count) for c in counts) / avg_count if avg_count > 0 else 0

            print(f"平均负载: {avg_count:.0f}")
            print(f"最大偏差: {max_deviation:.2%}")

            # 负载应该相对均衡（偏差小于50%）
            assert max_deviation < 0.5
        finally:
            engine.stop()

    @pytest.mark.slow
    def test_symbol_ordering_guarantee(self):
        """测试相同交易对顺序保证"""
        engine = ConcurrentEventEngine(num_shards=4, max_queue_size_per_shard=1000)
        results = {}
        lock = threading.Lock()

        def handler(data):
            symbol = data["symbol"]
            seq = data["seq"]
            with lock:
                if symbol not in results:
                    results[symbol] = []
                results[symbol].append(seq)

        engine.register("SEQ", handler)
        engine.start()

        try:
            # 为每个交易对发送有序事件
            symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
            for seq in range(100):
                for symbol in symbols:
                    engine.put("SEQ", {"symbol": symbol, "seq": seq}, symbol=symbol)

            time.sleep(2)

            # 验证每个交易对的事件顺序
            for symbol in symbols:
                sequences = results.get(symbol, [])
                assert len(sequences) == 100, f"{symbol} 事件数量不匹配"
                assert sequences == list(range(100)), f"{symbol} 事件顺序错误"

            print("\n相同交易对顺序保证验证通过")
        finally:
            engine.stop()
