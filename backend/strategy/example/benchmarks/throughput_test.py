"""
吞吐量测试

测试各引擎在不同负载下的吞吐量表现。
"""

import time
import asyncio
from typing import Dict, Any, List
from loguru import logger

from .base import BenchmarkBase, BenchmarkResult
from strategy.core import (
    OptimizedEventEngine,
    create_async_engine,
    create_concurrent_engine,
)


class ThroughputTest(BenchmarkBase):
    """
    吞吐量测试

    测试各引擎在不同事件数量下的吞吐量表现。
    """

    def __init__(self):
        super().__init__("ThroughputTest")
        self.test_cases = [1000, 10000, 100000]
        self.results: Dict[str, List[BenchmarkResult]] = {}

    def _test_optimized_engine(self, num_events: int) -> BenchmarkResult:
        """测试优化事件引擎"""
        engine = OptimizedEventEngine(
            max_queue_size=max(num_events, 100000),
            num_workers=4,
        )
        event_count = [0]

        def handler(data):
            event_count[0] += 1

        engine.register("test", handler)
        engine.start()

        start_time = time.time()
        for i in range(num_events):
            engine.put("test", {"id": i})

        # 等待处理完成
        while event_count[0] < num_events:
            time.sleep(0.1)

        duration_ms = (time.time() - start_time) * 1000
        engine.stop()

        throughput = num_events / (duration_ms / 1000)

        return BenchmarkResult(
            name=f"OptimizedEngine_{num_events}",
            duration_ms=duration_ms,
            iterations=num_events,
            throughput=throughput,
            avg_latency_ms=duration_ms / num_events,
            min_latency_ms=0,
            max_latency_ms=0,
            memory_mb=0,
            cpu_percent=0,
        )

    def _test_async_engine(self, num_events: int) -> BenchmarkResult:
        """测试异步事件引擎"""
        async def run_test():
            engine = create_async_engine(
                max_queue_size=max(num_events, 100000),
                num_workers=8,
            )
            event_count = [0]

            async def handler(data):
                event_count[0] += 1

            await engine.register_async("test", handler)
            await engine.start()

            start_time = time.time()
            for i in range(num_events):
                await engine.put("test", {"id": i})

            # 等待处理完成
            while event_count[0] < num_events:
                await asyncio.sleep(0.1)

            duration_ms = (time.time() - start_time) * 1000
            await engine.stop()

            throughput = num_events / (duration_ms / 1000)

            return BenchmarkResult(
                name=f"AsyncEngine_{num_events}",
                duration_ms=duration_ms,
                iterations=num_events,
                throughput=throughput,
                avg_latency_ms=duration_ms / num_events,
                min_latency_ms=0,
                max_latency_ms=0,
                memory_mb=0,
                cpu_percent=0,
            )

        return asyncio.run(run_test())

    def _test_concurrent_engine(self, num_events: int) -> BenchmarkResult:
        """测试并发事件引擎"""
        symbols = [f"SYM{i}" for i in range(100)]
        engine = create_concurrent_engine(
            num_shards=16,
            max_queue_size_per_shard=max(num_events // 16, 10000),
        )
        event_count = [0]

        def handler(data):
            event_count[0] += 1

        engine.register("test", handler)
        engine.start()

        start_time = time.time()
        for i in range(num_events):
            symbol = symbols[i % len(symbols)]
            engine.put("test", {"id": i}, symbol=symbol)

        # 等待处理完成
        while event_count[0] < num_events:
            time.sleep(0.1)

        duration_ms = (time.time() - start_time) * 1000
        engine.stop()

        throughput = num_events / (duration_ms / 1000)

        return BenchmarkResult(
            name=f"ConcurrentEngine_{num_events}",
            duration_ms=duration_ms,
            iterations=num_events,
            throughput=throughput,
            avg_latency_ms=duration_ms / num_events,
            min_latency_ms=0,
            max_latency_ms=0,
            memory_mb=0,
            cpu_percent=0,
        )

    def execute(self) -> Dict[str, List[BenchmarkResult]]:
        """
        执行吞吐量测试

        Returns:
            Dict[str, List[BenchmarkResult]]: 各引擎在不同负载下的测试结果
        """
        logger.info("开始吞吐量测试")

        self.results["optimized"] = []
        self.results["async"] = []
        self.results["concurrent"] = []

        for num_events in self.test_cases:
            logger.info(f"\n测试 {num_events:,} 事件...")

            self.results["optimized"].append(
                self._test_optimized_engine(num_events)
            )
            self.results["async"].append(
                self._test_async_engine(num_events)
            )
            self.results["concurrent"].append(
                self._test_concurrent_engine(num_events)
            )

        self._print_results()
        return self.results

    def _print_results(self):
        """打印测试结果"""
        logger.info("\n" + "=" * 60)
        logger.info("吞吐量测试结果")
        logger.info("=" * 60)

        for engine_name, results in self.results.items():
            logger.info(f"\n{engine_name}:")
            for result in results:
                logger.info(
                    f"  {result.iterations:,} 事件: "
                    f"{result.throughput:,.0f} events/s"
                )

        logger.info("=" * 60)

    def get_throughput_chart_data(self) -> Dict[str, Any]:
        """
        获取吞吐量图表数据

        Returns:
            Dict: 可用于绘制图表的数据
        """
        return {
            "labels": [f"{n:,}" for n in self.test_cases],
            "datasets": [
                {
                    "label": engine_name,
                    "data": [r.throughput for r in results],
                }
                for engine_name, results in self.results.items()
            ],
        }
