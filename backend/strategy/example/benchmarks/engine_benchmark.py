"""
引擎对比基准测试

对比不同事件引擎的性能表现。
"""

import time
import numpy as np
from typing import Dict, Any, List
from loguru import logger

from .base import BenchmarkBase, BenchmarkResult
from strategy.core import (
    EventEngine,
    OptimizedEventEngine,
    AsyncEventEngine,
    ConcurrentEventEngine,
    create_async_engine,
    create_concurrent_engine,
)


class EngineBenchmark(BenchmarkBase):
    """
    引擎对比基准测试

    对比以下引擎的性能：
    1. 基础事件引擎 (EventEngine)
    2. 优化事件引擎 (OptimizedEventEngine)
    3. 异步事件引擎 (AsyncEventEngine)
    4. 并发事件引擎 (ConcurrentEventEngine)
    """

    def __init__(self, num_events: int = 100000):
        super().__init__("EngineBenchmark")
        self.num_events = num_events
        self.results: Dict[str, BenchmarkResult] = {}

    def _benchmark_basic_engine(self) -> BenchmarkResult:
        """测试基础事件引擎"""
        logger.info("测试基础事件引擎...")

        engine = EventEngine()
        event_count = [0]

        def handler(data):
            event_count[0] += 1

        engine.register("test", handler)
        engine.start()

        start_time = time.time()
        for i in range(self.num_events):
            engine.put("test", {"id": i})

        # 等待处理完成
        time.sleep(2)
        engine.stop()

        duration_ms = (time.time() - start_time) * 1000
        throughput = event_count[0] / (duration_ms / 1000)

        return BenchmarkResult(
            name="BasicEventEngine",
            duration_ms=duration_ms,
            iterations=event_count[0],
            throughput=throughput,
            avg_latency_ms=duration_ms / event_count[0] if event_count[0] > 0 else 0,
            min_latency_ms=0,
            max_latency_ms=0,
            memory_mb=0,
            cpu_percent=0,
        )

    def _benchmark_optimized_engine(self) -> BenchmarkResult:
        """测试优化事件引擎"""
        logger.info("测试优化事件引擎...")

        engine = OptimizedEventEngine(
            max_queue_size=100000,
            num_workers=4,
            enable_backpressure=True,
        )
        event_count = [0]

        def handler(data):
            event_count[0] += 1

        engine.register("test", handler)
        engine.start()

        start_time = time.time()
        for i in range(self.num_events):
            engine.put("test", {"id": i})

        # 等待处理完成
        time.sleep(2)
        engine.stop()

        duration_ms = (time.time() - start_time) * 1000
        throughput = event_count[0] / (duration_ms / 1000)

        return BenchmarkResult(
            name="OptimizedEventEngine",
            duration_ms=duration_ms,
            iterations=event_count[0],
            throughput=throughput,
            avg_latency_ms=duration_ms / event_count[0] if event_count[0] > 0 else 0,
            min_latency_ms=0,
            max_latency_ms=0,
            memory_mb=0,
            cpu_percent=0,
        )

    def _benchmark_async_engine(self) -> BenchmarkResult:
        """测试异步事件引擎"""
        logger.info("测试异步事件引擎...")

        import asyncio

        async def run_async_test():
            engine = create_async_engine(
                max_queue_size=100000,
                num_workers=8,
                enable_backpressure=True,
            )
            event_count = [0]

            async def handler(data):
                event_count[0] += 1

            await engine.register_async("test", handler)
            await engine.start()

            start_time = time.time()
            for i in range(self.num_events):
                await engine.put("test", {"id": i})

            # 等待处理完成
            await asyncio.sleep(2)
            await engine.stop()

            duration_ms = (time.time() - start_time) * 1000
            throughput = event_count[0] / (duration_ms / 1000)

            return BenchmarkResult(
                name="AsyncEventEngine",
                duration_ms=duration_ms,
                iterations=event_count[0],
                throughput=throughput,
                avg_latency_ms=duration_ms / event_count[0] if event_count[0] > 0 else 0,
                min_latency_ms=0,
                max_latency_ms=0,
                memory_mb=0,
                cpu_percent=0,
            )

        return asyncio.run(run_async_test())

    def _benchmark_concurrent_engine(self) -> BenchmarkResult:
        """测试并发事件引擎"""
        logger.info("测试并发事件引擎...")

        symbols = [f"SYM{i}" for i in range(100)]
        engine = create_concurrent_engine(
            num_shards=16,
            max_queue_size_per_shard=10000,
            enable_backpressure=True,
        )
        event_count = [0]

        def handler(data):
            event_count[0] += 1

        engine.register("test", handler)
        engine.start()

        start_time = time.time()
        for i in range(self.num_events):
            symbol = symbols[i % len(symbols)]
            engine.put("test", {"id": i}, symbol=symbol)

        # 等待处理完成
        time.sleep(2)
        engine.stop()

        duration_ms = (time.time() - start_time) * 1000
        throughput = event_count[0] / (duration_ms / 1000)

        return BenchmarkResult(
            name="ConcurrentEventEngine",
            duration_ms=duration_ms,
            iterations=event_count[0],
            throughput=throughput,
            avg_latency_ms=duration_ms / event_count[0] if event_count[0] > 0 else 0,
            min_latency_ms=0,
            max_latency_ms=0,
            memory_mb=0,
            cpu_percent=0,
        )

    def execute(self) -> Dict[str, BenchmarkResult]:
        """
        执行所有引擎的基准测试

        Returns:
            Dict[str, BenchmarkResult]: 各引擎的测试结果
        """
        logger.info(f"开始引擎对比基准测试: {self.num_events} 事件")

        # 测试各引擎
        self.results["basic"] = self._benchmark_basic_engine()
        self.results["optimized"] = self._benchmark_optimized_engine()
        self.results["async"] = self._benchmark_async_engine()
        self.results["concurrent"] = self._benchmark_concurrent_engine()

        # 打印结果
        self._print_results()

        return self.results

    def _print_results(self):
        """打印测试结果"""
        logger.info("=" * 60)
        logger.info("引擎对比基准测试结果")
        logger.info("=" * 60)

        for name, result in self.results.items():
            logger.info(f"\n{name}:")
            logger.info(f"  吞吐量: {result.throughput:,.0f} events/s")
            logger.info(f"  平均延迟: {result.avg_latency_ms:.3f} ms")
            logger.info(f"  处理事件: {result.iterations:,}")
            logger.info(f"  耗时: {result.duration_ms:.0f} ms")

        # 计算性能提升
        if "basic" in self.results and "optimized" in self.results:
            basic_throughput = self.results["basic"].throughput
            optimized_throughput = self.results["optimized"].throughput
            improvement = (optimized_throughput / basic_throughput - 1) * 100
            logger.info(f"\n优化引擎相比基础引擎性能提升: {improvement:.1f}%")

        logger.info("=" * 60)

    def get_comparison_table(self) -> str:
        """
        获取对比表格

        Returns:
            str: Markdown格式的对比表格
        """
        lines = [
            "| 引擎 | 吞吐量 (events/s) | 平均延迟 (ms) | 处理事件数 |",
            "|------|------------------|--------------|-----------|",
        ]

        for name, result in self.results.items():
            lines.append(
                f"| {name} | {result.throughput:,.0f} | "
                f"{result.avg_latency_ms:.3f} | {result.iterations:,} |"
            )

        return "\n".join(lines)
