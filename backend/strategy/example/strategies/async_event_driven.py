"""
异步事件驱动策略

利用 AsyncEventEngine 实现基于 asyncio 的高性能事件处理。
展示以下特性：
1. 真正的异步事件处理
2. 协程级别的并发
3. 低延迟事件响应
4. 背压机制
"""

import asyncio
import time
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from collections import defaultdict
from loguru import logger

from strategy.core import (
    AsyncEventEngine,
    create_async_engine,
)
from strategy.core.async_event_engine import EventPriority


@dataclass
class AsyncSignal:
    """异步交易信号"""
    timestamp: float
    symbol: str
    direction: str
    price: float
    latency_ms: float
    worker_id: int = 0


@dataclass
class MarketEvent:
    """市场事件"""
    event_type: str
    symbol: str
    data: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)
    priority: int = 2  # EventPriority.NORMAL


class AsyncEventDrivenStrategy:
    """
    异步事件驱动策略

    使用 AsyncEventEngine 基于 asyncio 实现真正异步的事件处理，
    支持数千并发任务，延迟更低，吞吐量更高。

    特性：
    1. 基于 asyncio 的真正异步处理
    2. 协程级别的并发，支持数千并发任务
    3. 更低的延迟和更高的吞吐量
    4. 背压机制防止过载
    """

    def __init__(
        self,
        symbols: List[str],
        num_workers: int = 8,
        max_queue_size: int = 100000,
        latency_threshold_ms: float = 1.0,
    ):
        """
        初始化策略

        Args:
            symbols: 交易对列表
            num_workers: 工作协程数量
            max_queue_size: 最大队列大小
            latency_threshold_ms: 延迟阈值（毫秒）
        """
        self.symbols = symbols
        self.num_workers = num_workers
        self.max_queue_size = max_queue_size
        self.latency_threshold_ms = latency_threshold_ms

        # 创建异步事件引擎
        self.engine = create_async_engine(
            max_queue_size=max_queue_size,
            num_workers=num_workers,
            enable_backpressure=True,
        )

        # 事件处理器
        self._handlers: Dict[str, List[Callable]] = defaultdict(list)

        # 性能监控
        self.latencies: List[float] = []
        self.signals: List[AsyncSignal] = []
        self.stats = {
            "total_events": 0,
            "events_by_type": defaultdict(int),
            "signals_generated": 0,
            "avg_latency_ms": 0.0,
            "max_latency_ms": 0.0,
            "p99_latency_ms": 0.0,
        }

        logger.info(
            f"异步事件驱动策略初始化完成: "
            f"symbols={len(symbols)}, workers={num_workers}"
        )

    async def register_handler(self, event_type: str, handler: Callable):
        """
        注册事件处理器

        Args:
            event_type: 事件类型
            handler: 处理器函数
        """
        self._handlers[event_type].append(handler)
        await self.engine.register_async(event_type, handler)

    async def on_market_data(self, event: MarketEvent):
        """
        处理市场数据事件

        Args:
            event: 市场事件
        """
        start_time = time.time()

        # 计算延迟
        latency_ms = (start_time - event.timestamp) * 1000
        self.latencies.append(latency_ms)

        # 更新统计
        self.stats["total_events"] += 1
        self.stats["events_by_type"][event.event_type] += 1

        # 生成交易信号
        if event.event_type == "tick":
            signal = await self._generate_signal(event)
            if signal:
                self.signals.append(signal)
                self.stats["signals_generated"] += 1

        # 更新延迟统计
        self._update_latency_stats()

    async def _generate_signal(self, event: MarketEvent) -> Optional[AsyncSignal]:
        """
        生成交易信号

        Args:
            event: 市场事件

        Returns:
            AsyncSignal or None: 交易信号
        """
        # 模拟信号生成逻辑
        price = event.data.get("price", 0.0)

        # 简单的均值回归策略
        if price > 0:
            # 模拟计算延迟
            await asyncio.sleep(0.0001)  # 0.1ms

            direction = "buy" if price < 100 else "sell"

            return AsyncSignal(
                timestamp=time.time(),
                symbol=event.symbol,
                direction=direction,
                price=price,
                latency_ms=(time.time() - event.timestamp) * 1000,
            )

        return None

    def _update_latency_stats(self):
        """更新延迟统计"""
        if not self.latencies:
            return

        self.stats["avg_latency_ms"] = sum(self.latencies) / len(self.latencies)
        self.stats["max_latency_ms"] = max(self.latencies)

        # 计算 P99 延迟
        sorted_latencies = sorted(self.latencies)
        n = len(sorted_latencies)

        # 确保至少有2个样本才计算P99
        if n >= 2:
            p99_index = min(int(n * 0.99), n - 1)
            self.stats["p99_latency_ms"] = sorted_latencies[p99_index]
        else:
            self.stats["p99_latency_ms"] = sorted_latencies[0] if n == 1 else 0.0

    async def submit_event(
        self,
        event_type: str,
        symbol: str,
        data: Dict[str, Any],
        priority: EventPriority = EventPriority.NORMAL,
    ) -> bool:
        """
        提交事件

        Args:
            event_type: 事件类型
            symbol: 交易对
            data: 事件数据
            priority: 事件优先级

        Returns:
            bool: 是否成功提交
        """
        event = MarketEvent(
            event_type=event_type,
            symbol=symbol,
            data=data,
            timestamp=time.time(),
            priority=priority.value,
        )

        return await self.engine.put(
            event_type=event_type,
            data={
                "symbol": symbol,
                "data": data,
                "timestamp": event.timestamp,
            },
            priority=priority,
        )

    async def simulate_high_frequency_data(
        self,
        duration_seconds: float = 5.0,
        events_per_second: int = 10000,
    ) -> Dict[str, Any]:
        """
        模拟高频数据流

        Args:
            duration_seconds: 模拟时长（秒）
            events_per_second: 每秒事件数

        Returns:
            Dict: 模拟结果统计
        """
        start_time = time.time()
        event_count = 0

        logger.info(
            f"开始高频数据模拟: duration={duration_seconds}s, "
            f"rate={events_per_second}events/s"
        )

        # 创建事件生成任务
        async def generate_events():
            nonlocal event_count
            end_time = start_time + duration_seconds

            while time.time() < end_time:
                for symbol in self.symbols:
                    # 生成Tick事件
                    price = 100.0 + (hash(symbol) % 1000) / 100.0
                    data = {"price": price, "volume": 1000.0}

                    await self.submit_event(
                        event_type="tick",
                        symbol=symbol,
                        data=data,
                        priority=EventPriority.NORMAL,
                    )
                    event_count += 1

                # 控制生成速率
                await asyncio.sleep(1.0 / events_per_second)

        # 运行模拟
        await generate_events()

        # 等待所有事件处理完成
        await self.engine.wait_for_completion()

        total_time = time.time() - start_time

        return {
            "total_events": event_count,
            "duration_seconds": total_time,
            "events_per_second": event_count / total_time,
            "avg_latency_ms": self.stats["avg_latency_ms"],
            "max_latency_ms": self.stats["max_latency_ms"],
            "p99_latency_ms": self.stats["p99_latency_ms"],
        }

    async def run_latency_benchmark(
        self,
        num_events: int = 100000,
    ) -> Dict[str, Any]:
        """
        运行延迟基准测试

        Args:
            num_events: 事件数量

        Returns:
            Dict: 基准测试结果
        """
        self.reset()
        start_time = time.time()

        # 提交事件
        for i in range(num_events):
            symbol = self.symbols[i % len(self.symbols)]
            await self.submit_event(
                event_type="tick",
                symbol=symbol,
                data={"price": 100.0 + i * 0.01, "volume": 1000.0},
                priority=EventPriority.NORMAL,
            )

        # 等待处理完成
        await self.engine.wait_for_completion()

        total_time = (time.time() - start_time) * 1000

        return {
            "num_events": num_events,
            "total_time_ms": total_time,
            "events_per_second": num_events / (total_time / 1000),
            "avg_latency_ms": self.stats["avg_latency_ms"],
            "max_latency_ms": self.stats["max_latency_ms"],
            "p99_latency_ms": self.stats["p99_latency_ms"],
        }

    async def start(self):
        """启动策略"""
        # 注册默认处理器
        await self.register_handler("tick", self._handle_tick)
        await self.register_handler("bar", self._handle_bar)

        await self.engine.start()
        logger.info("异步事件引擎已启动")

    async def stop(self):
        """停止策略"""
        await self.engine.stop()
        logger.info("异步事件引擎已停止")

    async def _handle_tick(self, data: Dict[str, Any]):
        """处理Tick事件"""
        event = MarketEvent(
            event_type="tick",
            symbol=data.get("symbol", "UNKNOWN"),
            data=data.get("data", {}),
            timestamp=data.get("timestamp", time.time()),
        )
        await self.on_market_data(event)

    async def _handle_bar(self, data: Dict[str, Any]):
        """处理K线事件"""
        event = MarketEvent(
            event_type="bar",
            symbol=data.get("symbol", "UNKNOWN"),
            data=data.get("data", {}),
            timestamp=data.get("timestamp", time.time()),
        )
        await self.on_market_data(event)

    def get_stats(self) -> Dict[str, Any]:
        """获取策略统计信息"""
        stats = self.stats.copy()

        # 添加引擎统计
        try:
            engine_stats = self.engine.get_metrics()
            stats["engine"] = engine_stats
        except Exception as e:
            logger.warning(f"获取引擎统计失败: {e}")

        stats["signal_count"] = len(self.signals)
        stats["latency_samples"] = len(self.latencies)

        return stats

    def reset(self):
        """重置策略状态"""
        self.latencies.clear()
        self.signals.clear()
        self.stats = {
            "total_events": 0,
            "events_by_type": defaultdict(int),
            "signals_generated": 0,
            "avg_latency_ms": 0.0,
            "max_latency_ms": 0.0,
            "p99_latency_ms": 0.0,
        }


# 同步包装函数，方便非异步代码调用
def run_async_strategy(
    strategy: AsyncEventDrivenStrategy,
    duration_seconds: float = 5.0,
) -> Dict[str, Any]:
    """
    运行异步策略（同步包装）

    Args:
        strategy: 异步策略实例
        duration_seconds: 运行时长

    Returns:
        Dict: 运行结果
    """
    async def _run():
        await strategy.start()
        result = await strategy.simulate_high_frequency_data(
            duration_seconds=duration_seconds
        )
        await strategy.stop()
        return result

    return asyncio.run(_run())
