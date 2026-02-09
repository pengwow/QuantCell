"""
延迟测试

测试各引擎的事件处理延迟。
"""

import time
import asyncio
import statistics
from typing import Dict, Any, List
from loguru import logger

from .base import BenchmarkBase, BenchmarkResult
from strategy.core import (
    OptimizedEventEngine,
    create_async_engine,
    create_concurrent_engine,
)


class LatencyTest(BenchmarkBase):
    """
    延迟测试

    测试各引擎的事件处理延迟分布。
    """

    def __init__(self):
        super().__init__("LatencyTest")
        self.num_events = 10000
        self.results: Dict[str, Dict[str, float]] = {}

    def _test_optimized_engine(self) -> Dict[str, float]:
        """测试优化事件引擎延迟"""
        engine = OptimizedEventEngine(
            max_queue_size=100000,
            num_workers=4,
        )
        latencies: List[float] = []

        def handler(data):
            end_time = time.time()
            start_time = data.get("timestamp", end_time)
            latency_ms = (end_time - start_time) * 1000
            latencies.append(latency_ms)

        engine.register("test", handler)
        engine.start()

        # 发送事件
        for i in range(self.num_events):
            engine.put("test", {"id": i, "timestamp": time.time()})

        # 等待处理完成
        while len(latencies) < self.num_events:
            time.sleep(0.1)

        engine.stop()

        return self._calculate_latency_stats(latencies)

    def _test_async_engine(self) -> Dict[str, float]:
        """测试异步事件引擎延迟"""
        async def run_test():
            engine = create_async_engine(
                max_queue_size=100000,
                num_workers=8,
            )
            latencies: List[float] = []

            async def handler(data):
                end_time = time.time()
                start_time = data.get("timestamp", end_time)
                latency_ms = (end_time - start_time) * 1000
                latencies.append(latency_ms)

            await engine.register_async("test", handler)
            await engine.start()

            # 发送事件
            for i in range(self.num_events):
                await engine.put("test", {"id": i, "timestamp": time.time()})

            # 等待处理完成
            while len(latencies) < self.num_events:
                await asyncio.sleep(0.1)

            await engine.stop()

            return self._calculate_latency_stats(latencies)

        return asyncio.run(run_test())

    def _test_concurrent_engine(self) -> Dict[str, float]:
        """测试并发事件引擎延迟"""
        symbols = [f"SYM{i}" for i in range(100)]
        engine = create_concurrent_engine(
            num_shards=16,
            max_queue_size_per_shard=10000,
        )
        latencies: List[float] = []

        def handler(data):
            end_time = time.time()
            start_time = data.get("timestamp", end_time)
            latency_ms = (end_time - start_time) * 1000
            latencies.append(latency_ms)

        engine.register("test", handler)
        engine.start()

        # 发送事件
        for i in range(self.num_events):
            symbol = symbols[i % len(symbols)]
            engine.put("test", {"id": i, "timestamp": time.time()}, symbol=symbol)

        # 等待处理完成
        while len(latencies) < self.num_events:
            time.sleep(0.1)

        engine.stop()

        return self._calculate_latency_stats(latencies)

    def _calculate_latency_stats(self, latencies: List[float]) -> Dict[str, float]:
        """计算延迟统计"""
        if not latencies:
            return {}

        sorted_latencies = sorted(latencies)
        n = len(sorted_latencies)

        return {
            "min_ms": min(latencies),
            "max_ms": max(latencies),
            "avg_ms": statistics.mean(latencies),
            "median_ms": statistics.median(latencies),
            "p50_ms": sorted_latencies[int(n * 0.50)],
            "p90_ms": sorted_latencies[int(n * 0.90)],
            "p95_ms": sorted_latencies[int(n * 0.95)],
            "p99_ms": sorted_latencies[int(n * 0.99)],
            "std_ms": statistics.stdev(latencies) if len(latencies) > 1 else 0,
        }

    def execute(self) -> Dict[str, Dict[str, float]]:
        """
        执行延迟测试

        Returns:
            Dict[str, Dict[str, float]]: 各引擎的延迟统计
        """
        logger.info(f"开始延迟测试: {self.num_events} 事件")

        self.results["optimized"] = self._test_optimized_engine()
        self.results["async"] = self._test_async_engine()
        self.results["concurrent"] = self._test_concurrent_engine()

        self._print_results()
        return self.results

    def _print_results(self):
        """打印测试结果"""
        logger.info("\n" + "=" * 60)
        logger.info("延迟测试结果")
        logger.info("=" * 60)

        for engine_name, stats in self.results.items():
            logger.info(f"\n{engine_name}:")
            logger.info(f"  最小延迟: {stats['min_ms']:.3f} ms")
            logger.info(f"  最大延迟: {stats['max_ms']:.3f} ms")
            logger.info(f"  平均延迟: {stats['avg_ms']:.3f} ms")
            logger.info(f"  中位数: {stats['median_ms']:.3f} ms")
            logger.info(f"  P90: {stats['p90_ms']:.3f} ms")
            logger.info(f"  P95: {stats['p95_ms']:.3f} ms")
            logger.info(f"  P99: {stats['p99_ms']:.3f} ms")
            logger.info(f"  标准差: {stats['std_ms']:.3f} ms")

        logger.info("=" * 60)

    def get_latency_comparison_table(self) -> str:
        """
        获取延迟对比表格

        Returns:
            str: Markdown格式的对比表格
        """
        lines = [
            "| 引擎 | 平均延迟 (ms) | P50 (ms) | P90 (ms) | P99 (ms) |",
            "|------|--------------|----------|----------|----------|",
        ]

        for engine_name, stats in self.results.items():
            lines.append(
                f"| {engine_name} | {stats['avg_ms']:.3f} | "
                f"{stats['p50_ms']:.3f} | {stats['p90_ms']:.3f} | "
                f"{stats['p99_ms']:.3f} |"
            )

        return "\n".join(lines)
