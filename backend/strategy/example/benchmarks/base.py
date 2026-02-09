"""
基准测试基类

提供基准测试的基础框架和通用功能。
"""

import time
import psutil
import os
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from loguru import logger


@dataclass
class BenchmarkResult:
    """基准测试结果"""
    name: str
    duration_ms: float
    iterations: int
    throughput: float  # items/second
    avg_latency_ms: float
    min_latency_ms: float
    max_latency_ms: float
    memory_mb: float
    cpu_percent: float
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "name": self.name,
            "duration_ms": self.duration_ms,
            "iterations": self.iterations,
            "throughput": self.throughput,
            "avg_latency_ms": self.avg_latency_ms,
            "min_latency_ms": self.min_latency_ms,
            "max_latency_ms": self.max_latency_ms,
            "memory_mb": self.memory_mb,
            "cpu_percent": self.cpu_percent,
            "metadata": self.metadata,
        }

    def __str__(self) -> str:
        """字符串表示"""
        return (
            f"BenchmarkResult({self.name}): "
            f"{self.throughput:.0f} items/s, "
            f"avg_latency={self.avg_latency_ms:.3f}ms, "
            f"memory={self.memory_mb:.1f}MB"
        )


class BenchmarkBase(ABC):
    """
    基准测试基类

    提供基准测试的基础功能：
    1. 性能测量
    2. 内存监控
    3. CPU监控
    4. 结果收集
    """

    def __init__(self, name: str, warmup_iterations: int = 100):
        """
        初始化基准测试

        Args:
            name: 测试名称
            warmup_iterations: 预热迭代次数
        """
        self.name = name
        self.warmup_iterations = warmup_iterations
        self.process = psutil.Process(os.getpid())
        self.results: List[BenchmarkResult] = []

    def _get_memory_usage(self) -> float:
        """获取当前内存使用（MB）"""
        return self.process.memory_info().rss / 1024 / 1024

    def _get_cpu_percent(self) -> float:
        """获取CPU使用率"""
        return self.process.cpu_percent()

    def warmup(self, warmup_func: callable):
        """
        执行预热

        Args:
            warmup_func: 预热函数
        """
        logger.info(f"开始预热: {self.warmup_iterations} 次迭代")
        for _ in range(self.warmup_iterations):
            warmup_func()
        logger.info("预热完成")

    def run(
        self,
        test_func: callable,
        iterations: int,
        setup_func: callable = None,
        teardown_func: callable = None,
    ) -> BenchmarkResult:
        """
        运行基准测试

        Args:
            test_func: 测试函数
            iterations: 迭代次数
            setup_func: 设置函数
            teardown_func: 清理函数

        Returns:
            BenchmarkResult: 测试结果
        """
        # 设置
        if setup_func:
            setup_func()

        # 收集性能数据
        latencies: List[float] = []
        start_memory = self._get_memory_usage()

        # 开始测试
        start_time = time.time()
        start_cpu = self._get_cpu_percent()

        for i in range(iterations):
            iter_start = time.time()
            test_func()
            iter_end = time.time()
            latencies.append((iter_end - iter_start) * 1000)

        end_time = time.time()
        end_cpu = self._get_cpu_percent()
        end_memory = self._get_memory_usage()

        # 清理
        if teardown_func:
            teardown_func()

        # 计算结果
        duration_ms = (end_time - start_time) * 1000
        throughput = iterations / (duration_ms / 1000)

        result = BenchmarkResult(
            name=self.name,
            duration_ms=duration_ms,
            iterations=iterations,
            throughput=throughput,
            avg_latency_ms=sum(latencies) / len(latencies),
            min_latency_ms=min(latencies),
            max_latency_ms=max(latencies),
            memory_mb=end_memory - start_memory,
            cpu_percent=end_cpu,
        )

        self.results.append(result)
        return result

    @abstractmethod
    def execute(self) -> BenchmarkResult:
        """
        执行基准测试

        Returns:
            BenchmarkResult: 测试结果
        """
        pass

    def get_summary(self) -> Dict[str, Any]:
        """获取测试摘要"""
        if not self.results:
            return {}

        return {
            "name": self.name,
            "total_tests": len(self.results),
            "avg_throughput": sum(r.throughput for r in self.results) / len(self.results),
            "avg_latency_ms": sum(r.avg_latency_ms for r in self.results) / len(self.results),
            "total_memory_mb": sum(r.memory_mb for r in self.results),
            "results": [r.to_dict() for r in self.results],
        }
