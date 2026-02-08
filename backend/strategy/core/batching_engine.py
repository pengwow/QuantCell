"""
批处理引擎 - 支持微批处理和向量化执行

基于设计文档中的第二阶段优化要求实现：
1. 微批处理（10ms或100事件）
2. 向量化策略执行
3. 批量订单提交
4. 减少Python循环开销
"""

import threading
import time
import logging
from typing import Dict, List, Callable, Any, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
from enum import IntEnum
import numpy as np
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)


class BatchStrategyType(IntEnum):
    """批处理策略类型"""
    TIME_BASED = 0      # 基于时间窗口
    SIZE_BASED = 1      # 基于批次大小
    HYBRID = 2          # 混合策略（时间和大小）


# 保持向后兼容的别名
BatchStrategyTypeAlias = BatchStrategyType


class BatchStrategy:
    """
    批处理策略

    根据批次大小和等待时间决定是否刷新批次。
    """

    def __init__(self, max_batch_size: int = 100, max_wait_time_ms: float = 10.0):
        """
        初始化批处理策略

        Args:
            max_batch_size: 最大批次大小
            max_wait_time_ms: 最大等待时间（毫秒）
        """
        self.max_batch_size = max_batch_size
        self.max_wait_time_ms = max_wait_time_ms
        self._created_at = time.time()
        self._event_count = 0

    def should_flush(self, event_count: int) -> bool:
        """
        检查是否应该刷新批次

        Args:
            event_count: 当前事件数量

        Returns:
            bool: 是否应该刷新
        """
        # 检查批次大小
        if event_count >= self.max_batch_size:
            return True

        # 检查等待时间
        elapsed_ms = (time.time() - self._created_at) * 1000
        if elapsed_ms >= self.max_wait_time_ms:
            return True

        return False

    def reset_timer(self) -> None:
        """重置计时器"""
        self._created_at = time.time()


@dataclass
class BatchEvent:
    """批处理事件"""
    event_type: str
    symbol: str
    data: Any
    timestamp: float = field(default_factory=time.time)


@dataclass
class EventBatch:
    """事件批次"""
    symbol: str = ""  # 交易对符号
    events: List[BatchEvent] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    max_size: int = 100  # 最大批次大小

    def add(self, event: Any) -> None:
        """添加事件到批次"""
        if isinstance(event, BatchEvent):
            self.events.append(event)
        else:
            self.events.append(event)

    def __len__(self) -> int:
        """获取批次事件数量"""
        return len(self.events)

    def size(self) -> int:
        """获取批次大小"""
        return len(self.events)

    def is_full(self) -> bool:
        """检查批次是否已满"""
        return len(self.events) >= self.max_size

    def age_ms(self) -> float:
        """获取批次年龄（毫秒）"""
        return (time.time() - self.created_at) * 1000

    def clear(self) -> None:
        """清空批次"""
        self.events.clear()
        self.created_at = time.time()

    def get_events(self) -> List[Any]:
        """获取所有事件"""
        return self.events.copy()

    def __iter__(self):
        """迭代器支持"""
        return iter(self.events)


class BatchingMetrics:
    """批处理引擎性能指标"""

    def __init__(self):
        self.batches_created = 0
        self.batches_processed = 0
        self.events_batched = 0
        self.events_processed = 0
        self.avg_batch_size = 0.0
        self.avg_batch_age_ms = 0.0
        self.processing_times: List[float] = []
        self._lock = threading.Lock()

    def record_batch_created(self, size: int):
        """记录批次创建"""
        with self._lock:
            self.batches_created += 1
            self.events_batched += size
    
    def record_batch_processed(self, size: int, age_ms: float, processing_time: float):
        """记录批次处理完成"""
        with self._lock:
            self.batches_processed += 1
            self.events_processed += size
            self.avg_batch_size = (self.avg_batch_size * (self.batches_processed - 1) + size) / self.batches_processed
            self.avg_batch_age_ms = (self.avg_batch_age_ms * (self.batches_processed - 1) + age_ms) / self.batches_processed
            self.processing_times.append(processing_time)
            if len(self.processing_times) > 1000:
                self.processing_times = self.processing_times[-1000:]
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            avg_processing_time = sum(self.processing_times) / len(self.processing_times) if self.processing_times else 0

            return {
                "batches_created": self.batches_created,
                "batches_processed": self.batches_processed,
                "events_batched": self.events_batched,
                "events_processed": self.events_processed,
                "avg_batch_size": self.avg_batch_size,
                "avg_batch_age_ms": self.avg_batch_age_ms,
                "avg_processing_time_ms": avg_processing_time * 1000,
                "batch_efficiency": self.events_processed / max(self.events_batched, 1)
            }


class SymbolBatchBuffer:
    """交易对批次缓冲区"""
    
    def __init__(
        self,
        symbol: str,
        max_batch_size: int = 100,
        max_batch_age_ms: float = 10.0
    ):
        self.symbol = symbol
        self.max_batch_size = max_batch_size
        self.max_batch_age_ms = max_batch_age_ms
        self.batch = EventBatch(symbol=symbol)
        self._lock = threading.RLock()
        self._last_flush_time = time.time()
    
    def add(self, event: BatchEvent) -> Optional[EventBatch]:
        """
        添加事件到缓冲区
        
        Returns:
            EventBatch or None: 如果批次已满或超时，返回批次
        """
        with self._lock:
            self.batch.add(event)
            
            # 检查是否需要刷新
            if self.batch.size() >= self.max_batch_size:
                return self._flush()
            
            if self.batch.age_ms() >= self.max_batch_age_ms:
                return self._flush()
            
            return None
    
    def flush(self) -> Optional[EventBatch]:
        """强制刷新缓冲区"""
        with self._lock:
            if self.batch.size() > 0:
                return self._flush()
            return None
    
    def _flush(self) -> EventBatch:
        """内部刷新方法"""
        batch = EventBatch(
            symbol=self.symbol,
            events=self.batch.events.copy(),
            created_at=self.batch.created_at
        )
        self.batch.clear()
        self._last_flush_time = time.time()
        return batch
    
    def should_flush(self) -> bool:
        """检查是否应该刷新"""
        with self._lock:
            if self.batch.size() == 0:
                return False
            return self.batch.age_ms() >= self.max_batch_age_ms


class BatchingEngine:
    """
    批处理引擎
    
    特性：
    1. 微批处理 - 按时间窗口或批次大小批量处理事件
    2. 向量化执行 - 使用NumPy进行批量计算
    3. 交易对级别批处理 - 每个交易对独立批处理
    4. 混合策略 - 支持时间和大小混合触发
    """
    
    def __init__(
        self,
        max_batch_size: int = 100,
        max_batch_age_ms: float = 10.0,
        batch_strategy: Any = None,
        num_workers: int = 4,
        enable_vectorization: bool = True,
        max_wait_time_ms: Optional[float] = None,
        max_queue_size: Optional[int] = None
    ):
        """
        初始化批处理引擎

        Args:
            max_batch_size: 最大批次大小，控制批处理内存使用
            max_batch_age_ms: 最大批次年龄（毫秒），控制批处理延迟
            batch_strategy: 批处理策略类型
            num_workers: 工作线程数量，控制并发处理能力
            enable_vectorization: 是否启用向量化计算，提升数值处理性能
            max_wait_time_ms: 最大等待时间（毫秒），max_batch_age_ms 的别名
            max_queue_size: 最大队列大小，控制事件缓冲容量
        """
        self.max_batch_size = max_batch_size
        self.max_batch_age_ms = max_wait_time_ms if max_wait_time_ms is not None else max_batch_age_ms
        self.batch_strategy = batch_strategy if batch_strategy is not None else BatchStrategyType.HYBRID
        self.num_workers = num_workers
        self.enable_vectorization = enable_vectorization
        self.max_queue_size = max_queue_size if max_queue_size is not None else max_batch_size * 10
        
        # 交易对缓冲区
        self.buffers: Dict[str, SymbolBatchBuffer] = {}
        self._buffers_lock = threading.RLock()
        
        # 批处理器
        self.batch_handlers: Dict[str, Callable] = {}
        self._handlers_lock = threading.RLock()
        
        # 工作线程
        self._executor = ThreadPoolExecutor(max_workers=num_workers)
        self._running = False
        self._flush_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        # 性能指标
        self.metrics = BatchingMetrics()
        
        strategy_name = batch_strategy.name if batch_strategy else "HYBRID"
        logger.info(f"批处理引擎初始化完成: 批次大小={max_batch_size}, "
                   f"批次年龄={max_batch_age_ms}ms, 策略={strategy_name}")
    
    def register(self, event_type: str, handler: Callable) -> None:
        """注册批处理器"""
        with self._handlers_lock:
            self.batch_handlers[event_type] = handler
            logger.debug(f"注册批处理器: {event_type}")
    
    def put(self, event_type: str, symbol: str, data: Any) -> bool:
        """
        添加事件到批处理引擎
        
        Args:
            event_type: 事件类型
            symbol: 交易对符号
            data: 事件数据
            
        Returns:
            bool: 是否成功添加
        """
        # 获取或创建缓冲区
        buffer = self._get_or_create_buffer(symbol)
        
        # 创建事件
        event = BatchEvent(
            event_type=event_type,
            symbol=symbol,
            data=data
        )
        
        # 添加到缓冲区
        batch = buffer.add(event)
        
        # 如果批次已满，提交处理
        if batch is not None:
            self._submit_batch(batch)
        
        return True
    
    def _get_or_create_buffer(self, symbol: str) -> SymbolBatchBuffer:
        """获取或创建交易对缓冲区"""
        with self._buffers_lock:
            if symbol not in self.buffers:
                self.buffers[symbol] = SymbolBatchBuffer(
                    symbol=symbol,
                    max_batch_size=self.max_batch_size,
                    max_batch_age_ms=self.max_batch_age_ms
                )
            return self.buffers[symbol]
    
    def _submit_batch(self, batch: EventBatch) -> None:
        """提交批次处理"""
        self.metrics.record_batch_created(batch.size())
        
        # 提交到线程池
        self._executor.submit(self._process_batch, batch)
    
    def _process_batch(self, batch: EventBatch) -> None:
        """处理批次"""
        start_time = time.time()
        
        try:
            # 按事件类型分组
            events_by_type: Dict[str, List[BatchEvent]] = defaultdict(list)
            for event in batch.events:
                events_by_type[event.event_type].append(event)
            
            # 处理每种事件类型
            for event_type, events in events_by_type.items():
                with self._handlers_lock:
                    handler = self.batch_handlers.get(event_type)
                
                if handler is None:
                    logger.warning(f"未找到批处理器: {event_type}")
                    continue
                
                # 调用批处理器
                if self.enable_vectorization:
                    self._process_vectorized(handler, events)
                else:
                    self._process_sequential(handler, events)
            
            # 记录处理时间
            processing_time = time.time() - start_time
            self.metrics.record_batch_processed(
                size=batch.size(),
                age_ms=batch.age_ms(),
                processing_time=processing_time
            )
            
        except Exception as e:
            logger.error(f"处理批次时出错: {e}")
    
    def _process_sequential(self, handler: Callable, events: List[BatchEvent]) -> None:
        """顺序处理事件"""
        for event in events:
            try:
                handler(event.data)
            except Exception as e:
                logger.error(f"处理事件时出错: {e}")
    
    def _process_vectorized(self, handler: Callable, events: List[BatchEvent]) -> None:
        """向量化处理事件"""
        try:
            # 提取数据
            data_list = [event.data for event in events]
            
            # 如果处理器支持向量化，传递整个列表
            if hasattr(handler, '__vectorized__'):
                handler(data_list)
            else:
                # 否则顺序处理
                self._process_sequential(handler, events)
                
        except Exception as e:
            logger.error(f"向量化处理时出错: {e}")
            # 回退到顺序处理
            self._process_sequential(handler, events)
    
    def _flush_loop(self) -> None:
        """定期刷新缓冲区"""
        while self._running and not self._stop_event.is_set():
            try:
                # 检查所有缓冲区
                buffers_to_flush = []
                with self._buffers_lock:
                    for symbol, buffer in list(self.buffers.items()):
                        if buffer.should_flush():
                            buffers_to_flush.append(buffer)
                
                # 刷新缓冲区
                for buffer in buffers_to_flush:
                    batch = buffer.flush()
                    if batch is not None:
                        self._submit_batch(batch)
                
                # 休眠一段时间
                time.sleep(self.max_batch_age_ms / 1000 / 2)
                
            except Exception as e:
                logger.error(f"刷新循环出错: {e}")
    
    def start(self) -> None:
        """启动批处理引擎"""
        if self._running:
            logger.warning("批处理引擎已在运行")
            return
        
        self._running = True
        self._stop_event.clear()
        
        # 启动刷新线程
        self._flush_thread = threading.Thread(
            target=self._flush_loop,
            name="BatchFlushThread",
            daemon=True
        )
        self._flush_thread.start()
        
        logger.info("批处理引擎已启动")
    
    def stop(self, timeout: float = 5.0) -> None:
        """停止批处理引擎"""
        if not self._running:
            return
        
        logger.info("正在停止批处理引擎...")
        self._running = False
        self._stop_event.set()
        
        # 等待刷新线程结束
        if self._flush_thread:
            self._flush_thread.join(timeout=1.0)
        
        # 刷新所有缓冲区
        with self._buffers_lock:
            for buffer in self.buffers.values():
                batch = buffer.flush()
                if batch is not None:
                    self._process_batch(batch)
        
        # 关闭线程池
        self._executor.shutdown(wait=True)
        
        logger.info("批处理引擎已停止")
        
        # 输出最终统计
        stats = self.metrics.get_stats()
        logger.info(f"最终统计: 批次={stats['batches_processed']}, "
                   f"事件={stats['events_processed']}, "
                   f"平均批次大小={stats['avg_batch_size']:.1f}")
    
    def flush_all(self) -> None:
        """强制刷新所有缓冲区"""
        with self._buffers_lock:
            for buffer in self.buffers.values():
                batch = buffer.flush()
                if batch is not None:
                    self._submit_batch(batch)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return self.metrics.get_stats()

    def get_metrics(self) -> Dict[str, Any]:
        """
        获取引擎性能指标

        Returns:
            Dict[str, Any]: 包含批次处理统计、事件计数、平均批次大小等指标
        """
        return self.metrics.get_stats()

    def get_buffer_stats(self) -> Dict[str, Any]:
        """
        获取缓冲区统计信息

        Returns:
            Dict[str, Any]: 包含缓冲区数量、缓冲事件总数、交易对列表等
        """
        with self._buffers_lock:
            return {
                "buffer_count": len(self.buffers),
                "total_buffered_events": sum(b.batch.size() for b in self.buffers.values()),
                "symbols": list(self.buffers.keys())[:100]  # 只返回前100个
            }

    @property
    def running(self) -> bool:
        """
        获取引擎运行状态

        Returns:
            bool: 引擎是否正在运行
        """
        return self._running

    def unregister(self, event_type: str, handler: Callable) -> bool:
        """
        注销事件处理器

        Args:
            event_type: 事件类型
            handler: 要注销的处理器函数

        Returns:
            bool: 是否成功注销
        """
        with self._handlers_lock:
            if event_type in self.batch_handlers and self.batch_handlers[event_type] == handler:
                del self.batch_handlers[event_type]
                return True
            return False

    def clear_handlers(self, event_type: str) -> None:
        """
        清空指定类型的所有处理器

        Args:
            event_type: 要清空处理器的事件类型
        """
        with self._handlers_lock:
            if event_type in self.batch_handlers:
                del self.batch_handlers[event_type]

    def get_all_handlers(self) -> Dict[str, Callable]:
        """
        获取所有已注册的处理器

        Returns:
            Dict[str, Callable]: 事件类型到处理器的映射
        """
        with self._handlers_lock:
            return self.batch_handlers.copy()

    def flush(self) -> None:
        """
        刷新所有缓冲区，强制处理所有待处理事件
        """
        self.flush_all()


class VectorizedBatchProcessor:
    """
    向量化批处理器
    
    使用NumPy进行批量计算，提高性能
    """
    
    def __init__(self):
        self._cache: Dict[str, np.ndarray] = {}
    
    def process_prices(self, prices: List[float]) -> Dict[str, float]:
        """
        向量化处理价格数据
        
        Args:
            prices: 价格列表
            
        Returns:
            Dict: 统计指标
        """
        if not prices:
            return {}
        
        # 转换为NumPy数组
        price_array = np.array(prices, dtype=np.float32)
        
        # 计算统计指标
        return {
            "mean": float(np.mean(price_array)),
            "std": float(np.std(price_array)),
            "min": float(np.min(price_array)),
            "max": float(np.max(price_array)),
            "change": float((price_array[-1] - price_array[0]) / price_array[0]) if price_array[0] != 0 else 0
        }
    
    def process_signals(self, signals: List[int]) -> Dict[str, int]:
        """
        向量化处理信号
        
        Args:
            signals: 信号列表（1=买入, -1=卖出, 0=持有）
            
        Returns:
            Dict: 信号统计
        """
        if not signals:
            return {}
        
        signal_array = np.array(signals, dtype=np.int8)
        
        return {
            "buy_count": int(np.sum(signal_array == 1)),
            "sell_count": int(np.sum(signal_array == -1)),
            "hold_count": int(np.sum(signal_array == 0)),
            "total": len(signals)
        }

    def calculate_sma(self, prices: List[float], period: int = 3) -> np.ndarray:
        """
        计算简单移动平均（SMA）

        Args:
            prices: 价格列表
            period: 移动平均周期，默认3

        Returns:
            np.ndarray: 简单移动平均值数组，前period-1个值为NaN
        """
        if not prices:
            return np.array([])
        price_array = np.array(prices, dtype=np.float64)
        sma = np.convolve(price_array, np.ones(period)/period, mode='same')
        sma[:period-1] = np.nan
        return sma

    def calculate_returns(self, prices: List[float]) -> np.ndarray:
        """
        计算收益率

        Args:
            prices: 价格列表

        Returns:
            np.ndarray: 收益率数组，第一个值为NaN
        """
        if not prices:
            return np.array([])
        price_array = np.array(prices, dtype=np.float64)
        returns = np.diff(price_array) / price_array[:-1]
        returns = np.insert(returns, 0, np.nan)
        return returns


class BatchStrategyConfig:
    """
    批处理策略配置

    用于配置批处理引擎的行为参数，包括批次大小、等待时间等。
    通过调整这些参数可以平衡吞吐量和延迟。
    """

    def __init__(self, max_batch_size: int = 100, max_wait_time_ms: float = 50.0):
        self.max_batch_size = max_batch_size
        self.max_wait_time_ms = max_wait_time_ms
        self._last_flush_time = time.time()

    def should_flush(self, batch: EventBatch) -> bool:
        """检查是否应该刷新批次"""
        if batch.size() == 0:
            return False
        if batch.size() >= self.max_batch_size:
            return True
        if batch.age_ms() >= self.max_wait_time_ms:
            return True
        return False

    def reset_timer(self) -> None:
        """重置计时器"""
        self._last_flush_time = time.time()


# 便捷函数
def create_batching_engine(
    max_batch_size: int = 100,
    max_batch_age_ms: float = 10.0,
    batch_strategy: Any = None,
    num_workers: int = 4
) -> BatchingEngine:
    """
    创建批处理引擎
    
    Args:
        max_batch_size: 最大批次大小
        max_batch_age_ms: 最大批次年龄（毫秒）
        batch_strategy: 批处理策略
        num_workers: 工作线程数量
        
    Returns:
        BatchingEngine: 批处理引擎实例
    """
    return BatchingEngine(
        max_batch_size=max_batch_size,
        max_batch_age_ms=max_batch_age_ms,
        batch_strategy=batch_strategy,
        num_workers=num_workers
    )


# 兼容性别名
BatchMetrics = BatchingMetrics
