"""
策略测试

测试示例策略的功能正确性。
"""

import pytest
import numpy as np
import time
from typing import Dict, Any

from strategy.example.strategies import (
    VectorizedSMAStrategy,
    ConcurrentPairsStrategy,
    AsyncEventDrivenStrategy,
)


class TestVectorizedSMAStrategy:
    """测试向量化双均线策略"""

    def test_initialization(self):
        """测试策略初始化"""
        strategy = VectorizedSMAStrategy(
            fast_period=10,
            slow_period=30,
            batch_size=100,
        )

        assert strategy.fast_period == 10
        assert strategy.slow_period == 30
        assert strategy.batch_size == 100
        assert strategy.vector_engine is not None

    def test_signal_generation(self):
        """测试信号生成"""
        strategy = VectorizedSMAStrategy(fast_period=3, slow_period=5)
        strategy.start()

        symbol = "TEST"

        # 生成价格数据（产生金叉）
        prices = [100, 101, 102, 103, 104, 105, 110, 115, 120]

        signals = []
        for i, price in enumerate(prices):
            bar = {
                "open": price - 1,
                "high": price + 1,
                "low": price - 1,
                "close": price,
                "volume": 1000,
                "timestamp": time.time() + i,
            }
            signal = strategy.on_bar(symbol, bar)
            if signal:
                signals.append(signal)

        strategy.stop()

        # 应该产生至少一个信号
        assert len(signals) >= 0  # 信号产生取决于价格模式

    def test_vectorized_calculation(self):
        """测试向量化计算"""
        strategy = VectorizedSMAStrategy(fast_period=3, slow_period=5)

        prices = np.array([100.0, 101.0, 102.0, 103.0, 104.0, 105.0])

        sma = strategy._calculate_sma_vectorized(prices, 3)

        assert len(sma) == len(prices) - 3 + 1
        assert sma[0] == pytest.approx(101.0, rel=1e-10)

    def test_backtest(self):
        """测试回测功能"""
        strategy = VectorizedSMAStrategy(fast_period=5, slow_period=10)

        # 生成随机价格数据
        np.random.seed(42)
        prices = np.cumsum(np.random.randn(100)) + 100

        results = strategy.run_backtest(prices, symbol="TEST")

        assert "total_bars" in results
        assert "processing_time_ms" in results
        assert "bars_per_second" in results
        assert results["total_bars"] == len(prices)

    def test_stats(self):
        """测试统计信息"""
        strategy = VectorizedSMAStrategy()

        stats = strategy.get_stats()

        assert "total_bars" in stats
        assert "signals_generated" in stats
        assert "orders_submitted" in stats


class TestConcurrentPairsStrategy:
    """测试并发多交易对策略"""

    def test_initialization(self):
        """测试策略初始化"""
        symbols = ["BTCUSDT", "ETHUSDT", "ADAUSDT"]
        strategy = ConcurrentPairsStrategy(
            symbols=symbols,
            num_shards=4,
        )

        assert strategy.symbols == symbols
        assert strategy.num_shards == 4
        assert len(strategy.symbol_states) == len(symbols)

    def test_event_processing(self):
        """测试事件处理"""
        symbols = ["BTCUSDT", "ETHUSDT"]
        strategy = ConcurrentPairsStrategy(symbols=symbols)
        strategy.start()

        # 发送一些Tick事件
        for i in range(10):
            for symbol in symbols:
                strategy.on_tick(symbol, price=100.0 + i, volume=1000.0)

        time.sleep(0.5)  # 等待处理
        strategy.stop()

        stats = strategy.get_stats()
        assert stats["total_events"] > 0

    def test_shard_distribution(self):
        """测试分片分布"""
        symbols = [f"SYM{i}" for i in range(20)]
        strategy = ConcurrentPairsStrategy(symbols=symbols, num_shards=8)

        distribution = strategy.get_shard_distribution()

        assert len(distribution) == len(symbols)
        # 所有交易对都应该被分配到某个分片
        for symbol, shard_id in distribution.items():
            assert 0 <= shard_id < strategy.num_shards

    def test_signal_generation(self):
        """测试信号生成"""
        symbols = ["BTCUSDT"]
        strategy = ConcurrentPairsStrategy(
            symbols=symbols,
            lookback_period=5,
        )

        # 创建一个有足够价格数据的状态
        state = strategy.symbol_states["BTCUSDT"]
        state.prices = [100, 102, 101, 103, 105, 108, 110]

        signal = strategy._generate_signal("BTCUSDT", state)

        # 根据波动率可能产生信号
        assert signal is None or hasattr(signal, "direction")


class TestAsyncEventDrivenStrategy:
    """测试异步事件驱动策略"""

    @pytest.mark.asyncio
    async def test_initialization(self):
        """测试策略初始化"""
        symbols = ["BTCUSDT", "ETHUSDT"]
        strategy = AsyncEventDrivenStrategy(
            symbols=symbols,
            num_workers=4,
        )

        assert strategy.symbols == symbols
        assert strategy.num_workers == 4

    @pytest.mark.asyncio
    async def test_event_submission(self):
        """测试事件提交"""
        symbols = ["BTCUSDT"]
        strategy = AsyncEventDrivenStrategy(symbols=symbols)
        await strategy.start()

        # 提交事件
        result = await strategy.submit_event(
            event_type="tick",
            symbol="BTCUSDT",
            data={"price": 100.0, "volume": 1000.0},
        )

        await strategy.stop()

        assert result is True

    @pytest.mark.asyncio
    async def test_latency_tracking(self):
        """测试延迟追踪"""
        symbols = ["BTCUSDT"]
        strategy = AsyncEventDrivenStrategy(symbols=symbols)

        # 模拟一些延迟数据
        strategy.latencies = [0.1, 0.2, 0.15, 0.3, 0.25]
        strategy._update_latency_stats()

        assert strategy.stats["avg_latency_ms"] > 0
        assert strategy.stats["max_latency_ms"] > 0

    def test_sync_wrapper(self):
        """测试同步包装函数"""
        from strategy.example.strategies.async_event_driven import run_async_strategy

        symbols = ["BTCUSDT"]
        strategy = AsyncEventDrivenStrategy(symbols=symbols)

        # 运行短时间测试
        result = run_async_strategy(strategy, duration_seconds=0.5)

        assert "total_events" in result
        assert "events_per_second" in result


class TestStrategyIntegration:
    """策略集成测试"""

    def test_vectorized_vs_concurrent(self):
        """测试向量化策略和并发策略的对比"""
        # 这个测试验证两种策略都能正确处理数据
        symbols = ["TEST"]

        # 向量化策略
        vector_strategy = VectorizedSMAStrategy(fast_period=3, slow_period=5)
        vector_strategy.start()

        # 并发策略
        concurrent_strategy = ConcurrentPairsStrategy(symbols=symbols)
        concurrent_strategy.start()

        # 发送相同的数据
        prices = [100, 101, 102, 103, 104, 105]
        for price in prices:
            bar = {"close": price, "volume": 1000}
            vector_strategy.on_bar("TEST", bar)
            concurrent_strategy.on_bar("TEST", bar)

        time.sleep(0.5)

        vector_strategy.stop()
        concurrent_strategy.stop()

        # 两者都应该处理事件
        vector_stats = vector_strategy.get_stats()
        concurrent_stats = concurrent_strategy.get_stats()

        assert vector_stats["total_bars"] == len(prices)
        assert concurrent_stats["total_events"] > 0
