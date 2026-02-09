"""
QuantCell 高性能策略执行模块演示

本演示展示 strategy/core 模块的高性能特性：
1. 向量化双均线策略 - 展示 NumPy 向量化计算性能
2. 并发多交易对策略 - 展示多交易对并行处理能力
3. 异步事件驱动策略 - 展示 asyncio 高性能事件处理
4. 引擎性能对比 - 对比各引擎的吞吐量和延迟
"""

import sys
import os
from pathlib import Path

# 添加 backend 目录到 Python 路径
backend_dir = Path(__file__).parent.parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import time
import numpy as np
import asyncio
from typing import Dict, Any
from loguru import logger

# 配置日志
logger.remove()
logger.add(sys.stderr, level="INFO", format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>")

from strategy.example.strategies import (
    VectorizedSMAStrategy,
    ConcurrentPairsStrategy,
    AsyncEventDrivenStrategy,
)
from strategy.example.benchmarks import (
    EngineBenchmark,
    ThroughputTest,
    LatencyTest,
)


class DemoRunner:
    """演示运行器"""

    def __init__(self):
        self.results: Dict[str, Any] = {}

    def print_header(self, title: str):
        """打印章节标题"""
        print("\n" + "=" * 70)
        print(f"  {title}")
        print("=" * 70 + "\n")

    def print_result(self, name: str, value: Any):
        """打印结果"""
        print(f"  {name:<30} {value}")

    def demo_vectorized_strategy(self):
        """演示向量化双均线策略"""
        self.print_header("演示 1: 向量化双均线策略")

        # 创建策略
        strategy = VectorizedSMAStrategy(
            fast_period=10,
            slow_period=30,
            batch_size=100,
            use_batching=True,
        )

        # 生成模拟价格数据
        np.random.seed(42)
        n_bars = 10000
        prices = np.cumsum(np.random.randn(n_bars) * 0.5) + 100

        logger.info(f"生成 {n_bars} 根K线数据")

        # 启动策略
        strategy.start()

        # 处理K线数据
        start_time = time.time()
        for i, price in enumerate(prices):
            bar = {
                "open": price - 0.5,
                "high": price + 1.0,
                "low": price - 1.0,
                "close": price,
                "volume": np.random.randint(1000, 10000),
                "timestamp": time.time() + i,
            }
            signal = strategy.on_bar("BTCUSDT", bar)
            if signal and i % 1000 == 0:
                logger.info(f"信号: {signal.direction} @ {signal.price:.2f}")

        processing_time = (time.time() - start_time) * 1000

        # 停止策略
        strategy.stop()

        # 获取统计
        stats = strategy.get_stats()

        print("\n  性能统计:")
        self.print_result("处理K线数", f"{stats['total_bars']:,}")
        self.print_result("生成信号数", stats['signals_generated'])
        self.print_result("处理时间", f"{processing_time:.2f} ms")
        self.print_result("K线处理速度", f"{n_bars / (processing_time / 1000):,.0f} bars/s")

        # 运行向量化回测
        print("\n  向量化回测:")
        backtest_results = strategy.run_backtest(prices, symbol="BTCUSDT")
        self.print_result("回测K线数", f"{backtest_results['total_bars']:,}")
        self.print_result("回测耗时", f"{backtest_results['processing_time_ms']:.2f} ms")
        self.print_result("回测速度", f"{backtest_results['bars_per_second']:,.0f} bars/s")

        self.results["vectorized"] = {
            "bars": n_bars,
            "signals": stats['signals_generated'],
            "processing_time_ms": processing_time,
            "backtest_time_ms": backtest_results['processing_time_ms'],
        }

    def demo_concurrent_strategy(self):
        """演示并发多交易对策略"""
        self.print_header("演示 2: 并发多交易对策略")

        # 创建交易对列表
        symbols = [
            "BTCUSDT", "ETHUSDT", "ADAUSDT", "SOLUSDT",
            "DOTUSDT", "LINKUSDT", "UNIUSDT", "AAVEUSDT",
        ]

        # 创建策略
        strategy = ConcurrentPairsStrategy(
            symbols=symbols,
            num_shards=8,
            lookback_period=20,
        )

        logger.info(f"初始化 {len(symbols)} 个交易对，使用 8 个分片")

        # 启动策略
        strategy.start()

        # 模拟市场数据
        print("\n  模拟市场数据流 (5秒)...")
        sim_results = strategy.simulate_market_data(
            duration_seconds=5.0,
            tick_rate=100.0,
        )

        # 停止策略
        strategy.stop()

        # 获取统计
        stats = strategy.get_stats()

        print("\n  性能统计:")
        self.print_result("模拟时长", f"{sim_results['duration_seconds']:.2f} s")
        self.print_result("总Tick数", f"{sim_results['total_ticks']:,}")
        self.print_result("Tick发送速率", f"{sim_results['ticks_per_second']:,.0f} ticks/s")
        self.print_result("处理事件数", f"{stats['total_events']:,}")
        self.print_result("生成信号数", stats['signals_generated'])

        # 显示分片分布
        print("\n  分片分布:")
        distribution = strategy.get_shard_distribution()
        for symbol, shard_id in sorted(distribution.items())[:4]:
            self.print_result(f"  {symbol}", f"分片 {shard_id}")
        print("  ...")

        # 显示引擎统计
        if 'engine' in stats:
            engine_stats = stats['engine']
            print("\n  引擎统计:")
            self.print_result("总处理事件", engine_stats.get('total_processed', 0))

        self.results["concurrent"] = {
            "symbols": len(symbols),
            "ticks": sim_results['total_ticks'],
            "tick_rate": sim_results['ticks_per_second'],
            "signals": stats['signals_generated'],
        }

    def demo_async_strategy(self):
        """演示异步事件驱动策略"""
        self.print_header("演示 3: 异步事件驱动策略")

        async def run_async_demo():
            # 创建交易对
            symbols = ["BTCUSDT", "ETHUSDT", "ADAUSDT"]

            # 创建策略
            strategy = AsyncEventDrivenStrategy(
                symbols=symbols,
                num_workers=8,
                max_queue_size=100000,
            )

            logger.info(f"初始化异步引擎，工作协程数: 8")

            # 启动策略
            await strategy.start()

            # 模拟高频数据
            print("\n  模拟高频数据流 (3秒)...")
            sim_results = await strategy.simulate_high_frequency_data(
                duration_seconds=3.0,
                events_per_second=5000,
            )

            # 停止策略
            await strategy.stop()

            # 获取统计
            stats = strategy.get_stats()

            print("\n  性能统计:")
            self.print_result("总事件数", f"{sim_results['total_events']:,}")
            self.print_result("事件发送速率", f"{sim_results['events_per_second']:,.0f} events/s")
            self.print_result("平均延迟", f"{sim_results['avg_latency_ms']:.3f} ms")
            self.print_result("P99延迟", f"{sim_results['p99_latency_ms']:.3f} ms")
            self.print_result("生成信号数", stats['signals_generated'])

            return {
                "events": sim_results['total_events'],
                "event_rate": sim_results['events_per_second'],
                "avg_latency_ms": sim_results['avg_latency_ms'],
                "p99_latency_ms": sim_results['p99_latency_ms'],
            }

        self.results["async"] = asyncio.run(run_async_demo())

    def demo_engine_benchmark(self):
        """演示引擎性能对比"""
        self.print_header("演示 4: 引擎性能对比")

        print("  运行引擎对比基准测试...\n")

        # 创建基准测试
        benchmark = EngineBenchmark(num_events=50000)

        # 执行测试
        results = benchmark.execute()

        # 打印对比表格
        print("\n" + benchmark.get_comparison_table())

        self.results["benchmark"] = {
            name: {
                "throughput": result.throughput,
                "latency_ms": result.avg_latency_ms,
            }
            for name, result in results.items()
        }

    def demo_throughput_test(self):
        """演示吞吐量测试"""
        self.print_header("演示 5: 吞吐量测试")

        print("  运行吞吐量测试...\n")

        # 创建测试
        test = ThroughputTest()

        # 执行测试
        results = test.execute()

        self.results["throughput"] = {
            engine: [
                {
                    "events": r.iterations,
                    "throughput": r.throughput,
                }
                for r in engine_results
            ]
            for engine, engine_results in results.items()
        }

    def demo_latency_test(self):
        """演示延迟测试"""
        self.print_header("演示 6: 延迟测试")

        print("  运行延迟测试...\n")

        # 创建测试
        test = LatencyTest()

        # 执行测试
        results = test.execute()

        # 打印对比表格
        print("\n" + test.get_latency_comparison_table())

        self.results["latency"] = results

    def print_summary(self):
        """打印总结"""
        self.print_header("演示总结")

        print("  本演示展示了 QuantCell 策略核心模块的高性能特性:\n")

        print("  1. 向量化双均线策略")
        if "vectorized" in self.results:
            r = self.results["vectorized"]
            print(f"     - 处理 {r['bars']:,} 根K线")
            print(f"     - 回测速度: {r['bars'] / (r['backtest_time_ms'] / 1000):,.0f} bars/s")

        print("\n  2. 并发多交易对策略")
        if "concurrent" in self.results:
            r = self.results["concurrent"]
            print(f"     - 支持 {r['symbols']} 个交易对并行处理")
            print(f"     - Tick处理速率: {r['tick_rate']:,.0f} ticks/s")

        print("\n  3. 异步事件驱动策略")
        if "async" in self.results:
            r = self.results["async"]
            print(f"     - 事件处理速率: {r['event_rate']:,.0f} events/s")
            print(f"     - 平均延迟: {r['avg_latency_ms']:.3f} ms")

        print("\n  4. 引擎性能对比")
        if "benchmark" in self.results:
            print("     各引擎吞吐量:")
            for name, stats in self.results["benchmark"].items():
                print(f"       - {name}: {stats['throughput']:,.0f} events/s")

        print("\n" + "=" * 70)
        print("  演示完成！")
        print("=" * 70)

    def run_all(self):
        """运行所有演示"""
        print("\n" + "=" * 70)
        print("  QuantCell 高性能策略执行模块演示")
        print("=" * 70)

        try:
            self.demo_vectorized_strategy()
        except Exception as e:
            logger.error(f"向量化策略演示失败: {e}")

        try:
            self.demo_concurrent_strategy()
        except Exception as e:
            logger.error(f"并发策略演示失败: {e}")

        try:
            self.demo_async_strategy()
        except Exception as e:
            logger.error(f"异步策略演示失败: {e}")

        try:
            self.demo_engine_benchmark()
        except Exception as e:
            logger.error(f"引擎对比演示失败: {e}")

        try:
            self.demo_throughput_test()
        except Exception as e:
            logger.error(f"吞吐量测试演示失败: {e}")

        try:
            self.demo_latency_test()
        except Exception as e:
            logger.error(f"延迟测试演示失败: {e}")

        self.print_summary()


def main():
    """主函数"""
    runner = DemoRunner()
    runner.run_all()


if __name__ == "__main__":
    main()
