"""
并发事件引擎 - 支持交易对分片和多工作线程并行处理

基于设计文档中的第二阶段优化要求实现：
1. 交易对分片处理（16-64分片）
2. 一致性哈希路由
3. 每交易对专用队列
4. 线程池管理
5. 符号级别的并发控制
"""

import threading
import time
import logging
from queue import Queue, Empty
from typing import Dict, List, Callable, Any, Optional, Set
from dataclasses import dataclass, field
from enum import IntEnum
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib

logger = logging.getLogger(__name__)


class EventPriority(IntEnum):
    """事件优先级定义"""
    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3
    BACKGROUND = 4


@dataclass
class SymbolEvent:
    """符号事件包装器"""
    event_type: str
    symbol: str
    data: Any
    priority: int = 2
    timestamp: float = field(default_factory=time.time)


class ShardRouter:
    """
    分片路由器 - 使用一致性哈希将交易对路由到对应分片
    """
    
    def __init__(self, num_shards: int = 16):
        self.num_shards = num_shards
        self._symbol_to_shard: Dict[str, int] = {}
        self._lock = threading.RLock()
    
    def get_shard(self, symbol: str) -> int:
        """
        获取交易对应的分片ID
        
        Args:
            symbol: 交易对符号
            
        Returns:
            int: 分片ID
        """
        with self._lock:
            if symbol in self._symbol_to_shard:
                return self._symbol_to_shard[symbol]
            
            # 计算哈希
            hash_value = int(hashlib.md5(symbol.encode()).hexdigest(), 16)
            shard_id = hash_value % self.num_shards
            
            # 缓存结果
            self._symbol_to_shard[symbol] = shard_id
            
            return shard_id
    
    def get_all_shards(self) -> List[int]:
        """获取所有分片ID"""
        return list(range(self.num_shards))
    
    def get_symbol_distribution(self) -> Dict[int, List[str]]:
        """获取交易对分布统计"""
        with self._lock:
            distribution: Dict[int, List[str]] = {i: [] for i in range(self.num_shards)}
            for symbol, shard_id in self._symbol_to_shard.items():
                distribution[shard_id].append(symbol)
            return distribution


class SymbolShard:
    """
    交易对分片 - 每个分片独立处理一组交易对
    
    特性：
    1. 独立的事件队列
    2. 独立的工作线程
    3. 符号级别的顺序保证
    """
    
    def __init__(self, shard_id: int, max_queue_size: int = 10000):
        self.shard_id = shard_id
        self.max_queue_size = max_queue_size
        self.queue = Queue(maxsize=max_queue_size)
        self.symbols: Set[str] = set()
        self._lock = threading.RLock()
        self._worker_thread: Optional[threading.Thread] = None
        self._running = False
        self._stop_event = threading.Event()
        
        # 统计
        self.events_processed = 0
        self.events_dropped = 0
    
    def add_symbol(self, symbol: str) -> None:
        """添加交易对到分片"""
        with self._lock:
            self.symbols.add(symbol)
    
    def remove_symbol(self, symbol: str) -> None:
        """从分片移除交易对"""
        with self._lock:
            self.symbols.discard(symbol)
    
    def has_symbol(self, symbol: str) -> bool:
        """检查分片是否包含交易对"""
        with self._lock:
            return symbol in self.symbols
    
    def put(self, event: SymbolEvent, block: bool = False, timeout: Optional[float] = None) -> bool:
        """添加事件到分片队列"""
        try:
            self.queue.put(event, block=block, timeout=timeout)
            return True
        except:
            self.events_dropped += 1
            return False

    def qsize(self) -> int:
        """
        获取当前队列大小

        Returns:
            int: 队列中待处理的事件数量
        """
        return self.queue.qsize()

    def start(self, handler_callback: Callable) -> None:
        """启动分片工作线程"""
        if self._running:
            return
        
        self._running = True
        self._stop_event.clear()
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            args=(handler_callback,),
            name=f"SymbolShard-{self.shard_id}",
            daemon=True
        )
        self._worker_thread.start()
        logger.debug(f"分片 {self.shard_id} 已启动")
    
    def stop(self, timeout: float = 2.0) -> None:
        """停止分片工作线程"""
        if not self._running:
            return
        
        self._running = False
        self._stop_event.set()
        
        if self._worker_thread:
            self._worker_thread.join(timeout=timeout)
        
        logger.debug(f"分片 {self.shard_id} 已停止，处理了 {self.events_processed} 个事件")
    
    def _worker_loop(self, handler_callback: Callable) -> None:
        """分片工作线程主循环"""
        while self._running and not self._stop_event.is_set():
            try:
                # 获取事件（带超时）
                event = self.queue.get(block=True, timeout=0.1)
                
                # 处理事件
                handler_callback(event)
                self.events_processed += 1
                
            except Empty:
                continue
            except Exception as e:
                logger.error(f"分片 {self.shard_id} 处理事件时出错: {e}")


class ConcurrentEventMetrics:
    """并发事件引擎性能指标"""
    
    def __init__(self, num_shards: int):
        self.num_shards = num_shards
        self.events_received = 0
        self.events_processed = 0
        self.events_dropped = 0
        self.events_by_shard: Dict[int, int] = {i: 0 for i in range(num_shards)}
        self.events_by_symbol: Dict[str, int] = {}
        self.processing_times: List[float] = []
        self._lock = threading.Lock()
    
    def record_received(self, shard_id: int, symbol: str):
        """记录接收事件"""
        with self._lock:
            self.events_received += 1
            self.events_by_shard[shard_id] = self.events_by_shard.get(shard_id, 0) + 1
            self.events_by_symbol[symbol] = self.events_by_symbol.get(symbol, 0) + 1
    
    def record_processed(self, processing_time: float):
        """记录处理完成事件"""
        with self._lock:
            self.events_processed += 1
            self.processing_times.append(processing_time)
            if len(self.processing_times) > 1000:
                self.processing_times = self.processing_times[-1000:]
    
    def record_dropped(self):
        """记录丢弃事件"""
        with self._lock:
            self.events_dropped += 1
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            avg_processing_time = sum(self.processing_times) / len(self.processing_times) if self.processing_times else 0

            return {
                "events_received": self.events_received,
                "events_processed": self.events_processed,
                "events_dropped": self.events_dropped,
                "events_by_shard": self.events_by_shard.copy(),
                "events_by_symbol": dict(list(self.events_by_symbol.items())[:100]),  # 只返回前100个
                "avg_processing_time_ms": avg_processing_time * 1000,
                "drop_rate": self.events_dropped / max(self.events_received, 1),
                "total_processed": self.events_processed,  # 总处理事件数（别名）
                "shard_metrics": [{"shard_id": i, "events": self.events_by_shard.get(i, 0)} for i in range(self.num_shards)],  # 各分片指标
                "total_queued": self.events_received - self.events_processed  # 队列中待处理事件数
            }


class ConcurrentEventEngine:
    """
    并发事件引擎 - 支持交易对分片并行处理
    
    特性：
    1. 交易对分片 - 将交易对分布到多个分片
    2. 一致性哈希 - 确保同一交易对始终路由到同一分片
    3. 独立队列 - 每个分片有独立的事件队列
    4. 并行处理 - 多个分片并行处理事件
    """
    
    def __init__(
        self,
        num_shards: int = 16,
        max_queue_size_per_shard: int = 10000,
        enable_backpressure: bool = True,
        backpressure_threshold: float = 0.8
    ):
        """
        初始化并发事件引擎

        Args:
            num_shards: 分片数量（建议为CPU核心数的2-4倍）
            max_queue_size_per_shard: 每个分片的最大队列大小
            enable_backpressure: 是否启用背压机制
            backpressure_threshold: 背压阈值
        """
        self.num_shards = num_shards
        self.max_queue_size_per_shard = max_queue_size_per_shard
        self.enable_backpressure = enable_backpressure
        self.backpressure_threshold = backpressure_threshold
        
        # 创建分片
        self.shards: List[SymbolShard] = [
            SymbolShard(shard_id=i, max_queue_size=max_queue_size_per_shard)
            for i in range(num_shards)
        ]
        
        # 交易对到分片的映射缓存
        self._symbol_to_shard: Dict[str, int] = {}
        
        # 事件处理器
        self.handlers: Dict[str, List[Callable]] = {}
        self._handlers_lock = threading.RLock()
        
        # 运行状态
        self._running = False
        
        # 性能指标
        self.metrics = ConcurrentEventMetrics(num_shards)
        
        # 背压状态
        self._backpressure_active = False
        self._dropped_count = 0
        
        logger.info(f"并发事件引擎初始化完成: {num_shards} 个分片, 每分片队列={max_queue_size_per_shard}")
    
    def _get_shard_id(self, symbol: str) -> int:
        """
        使用一致性哈希获取交易对应的分片ID
        
        Args:
            symbol: 交易对符号
            
        Returns:
            int: 分片ID
        """
        # 检查缓存
        if symbol in self._symbol_to_shard:
            return self._symbol_to_shard[symbol]
        
        # 计算哈希
        hash_value = int(hashlib.md5(symbol.encode()).hexdigest(), 16)
        shard_id = hash_value % self.num_shards
        
        # 缓存结果
        self._symbol_to_shard[symbol] = shard_id
        
        # 将交易对添加到分片
        self.shards[shard_id].add_symbol(symbol)
        
        return shard_id
    
    def register(self, event_type: str, handler: Callable) -> None:
        """注册事件处理器"""
        with self._handlers_lock:
            if event_type not in self.handlers:
                self.handlers[event_type] = []
            self.handlers[event_type].append(handler)
            logger.debug(f"注册事件处理器: {event_type}")
    
    def unregister(self, event_type: str, handler: Callable) -> bool:
        """注销事件处理器"""
        with self._handlers_lock:
            if event_type in self.handlers and handler in self.handlers[event_type]:
                self.handlers[event_type].remove(handler)
                return True
            return False
    
    def put(
        self,
        event_type: str,
        data: Any,
        symbol: str = "DEFAULT",
        priority: EventPriority = EventPriority.NORMAL,
        block: bool = False,
        timeout: Optional[float] = None
    ) -> bool:
        """
        添加事件到队列
        
        Args:
            event_type: 事件类型
            data: 事件数据
            symbol: 交易对符号，默认为 "DEFAULT"
            priority: 事件优先级
            block: 是否阻塞等待
            timeout: 阻塞超时时间
            
        Returns:
            bool: 是否成功添加
        """
        # 获取分片ID
        shard_id = self._get_shard_id(symbol)
        shard = self.shards[shard_id]
        
        # 背压检查
        if self.enable_backpressure and self._should_apply_backpressure(shard_id, priority):
            self.metrics.record_dropped()
            self._dropped_count += 1
            if self._dropped_count % 1000 == 1:
                logger.warning(f"背压机制激活，已丢弃 {self._dropped_count} 个事件")
            return False
        
        # 创建符号事件
        event = SymbolEvent(
            event_type=event_type,
            symbol=symbol,
            data=data,
            priority=priority.value
        )
        
        # 添加到分片队列
        success = shard.put(event, block=block, timeout=timeout)
        
        if success:
            self.metrics.record_received(shard_id, symbol)
            logger.debug(f"事件已添加: {event_type}, 交易对: {symbol}, 分片: {shard_id}")
        else:
            self.metrics.record_dropped()
            logger.warning(f"事件添加失败（队列已满）: {event_type}, 交易对: {symbol}")
        
        return success
    
    def _should_apply_backpressure(self, shard_id: int, priority: EventPriority) -> bool:
        """检查是否应该应用背压"""
        shard = self.shards[shard_id]
        queue_usage = shard.queue.qsize() / self.max_queue_size_per_shard
        
        if queue_usage >= self.backpressure_threshold:
            self._backpressure_active = True
            if priority.value >= EventPriority.NORMAL.value:
                return True
        else:
            # 检查所有分片的平均使用率
            total_usage = sum(s.queue.qsize() for s in self.shards) / (self.num_shards * self.max_queue_size_per_shard)
            if total_usage < self.backpressure_threshold:
                self._backpressure_active = False
        
        return False
    
    def _process_event(self, event: SymbolEvent) -> None:
        """处理单个事件"""
        start_time = time.time()
        
        with self._handlers_lock:
            handlers = self.handlers.get(event.event_type, [])
        
        if not handlers:
            logger.warning(f"未找到事件处理器: {event.event_type}")
            return
        
        # 顺序执行所有处理器
        for handler in handlers:
            try:
                handler(event.data)
            except Exception as e:
                logger.error(f"事件处理器执行失败: {event.event_type}, 错误: {e}")
        
        # 记录处理时间
        processing_time = time.time() - start_time
        self.metrics.record_processed(processing_time)
    
    def start(self) -> None:
        """启动事件引擎"""
        if self._running:
            logger.warning("并发事件引擎已在运行")
            return
        
        self._running = True
        
        # 启动所有分片
        for shard in self.shards:
            shard.start(self._process_event)
        
        logger.info(f"并发事件引擎已启动: {self.num_shards} 个分片")
    
    def stop(self, timeout: float = 5.0) -> None:
        """停止事件引擎"""
        if not self._running:
            return
        
        logger.info("正在停止并发事件引擎...")
        self._running = False
        
        # 停止所有分片
        for shard in self.shards:
            shard.stop(timeout=timeout / self.num_shards)
        
        logger.info("并发事件引擎已停止")
        
        # 输出最终统计
        stats = self.metrics.get_stats()
        logger.info(f"最终统计: 接收={stats['events_received']}, "
                   f"处理={stats['events_processed']}, "
                   f"丢弃={stats['events_dropped']}")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取事件引擎统计信息"""
        return self.metrics.get_stats()

    def get_metrics(self) -> Dict[str, Any]:
        """
        获取引擎性能指标

        Returns:
            Dict[str, Any]: 包含事件处理统计、队列状态、错误计数等指标
        """
        return self.metrics.get_stats()

    def is_healthy(self) -> bool:
        """
        检查引擎健康状态

        Returns:
            bool: 引擎是否健康（丢包率低于5%）
        """
        stats = self.metrics.get_stats()
        return stats['drop_rate'] < 0.05

    @property
    def running(self) -> bool:
        """
        获取引擎运行状态

        Returns:
            bool: 引擎是否正在运行
        """
        return self._running

    def clear_handlers(self, event_type: str) -> None:
        """
        清空指定类型的所有处理器

        Args:
            event_type: 要清空处理器的事件类型
        """
        with self._handlers_lock:
            if event_type in self.handlers:
                del self.handlers[event_type]

    def get_all_handlers(self) -> Dict[str, List[Callable]]:
        """
        获取所有已注册的处理器

        Returns:
            Dict[str, List[Callable]]: 事件类型到处理器列表的映射
        """
        with self._handlers_lock:
            return self.handlers.copy()
    
    def get_shard_stats(self, shard_id: int) -> Dict[str, Any]:
        """获取指定分片的统计信息"""
        if shard_id < 0 or shard_id >= self.num_shards:
            return {}
        
        shard = self.shards[shard_id]
        return {
            "shard_id": shard_id,
            "queue_size": shard.queue.qsize(),
            "symbols_count": len(shard.symbols),
            "events_processed": shard.events_processed,
            "events_dropped": shard.events_dropped
        }
    
    def rebalance_symbols(self, symbols: List[str]) -> Dict[str, int]:
        """
        重新平衡交易对分布
        
        Args:
            symbols: 所有交易对列表
            
        Returns:
            Dict[str, int]: 交易对到分片的映射
        """
        # 清空现有映射
        self._symbol_to_shard.clear()
        for shard in self.shards:
            shard.symbols.clear()
        
        # 重新分配
        mapping = {}
        for symbol in symbols:
            shard_id = self._get_shard_id(symbol)
            mapping[symbol] = shard_id
        
        logger.info(f"交易对重新平衡完成: {len(symbols)} 个交易对分布到 {self.num_shards} 个分片")
        return mapping


# 便捷函数
def create_concurrent_engine(
    num_shards: int = 16,
    max_queue_size_per_shard: int = 10000,
    enable_backpressure: bool = True
) -> ConcurrentEventEngine:
    """
    创建并发事件引擎
    
    Args:
        num_shards: 分片数量
        max_queue_size_per_shard: 每个分片的最大队列大小
        enable_backpressure: 是否启用背压
        
    Returns:
        ConcurrentEventEngine: 并发事件引擎实例
    """
    return ConcurrentEventEngine(
        num_shards=num_shards,
        max_queue_size_per_shard=max_queue_size_per_shard,
        enable_backpressure=enable_backpressure
    )
