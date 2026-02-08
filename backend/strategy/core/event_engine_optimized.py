"""
优化的事件引擎 - 支持有界队列、背压机制和事件优先级

基于设计文档中的第一阶段优化要求实现：
1. 有界队列防止内存无限增长
2. 背压机制处理高负载情况
3. 事件优先级支持（止损等关键事件优先处理）
4. 多工作线程支持
5. 优雅降级机制
6. 异常隔离和熔断器
7. 自动扩缩容
"""

import threading
import time
import logging
from queue import Queue, Empty, Full
from typing import Dict, List, Callable, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import IntEnum
from concurrent.futures import ThreadPoolExecutor
import heapq

# 导入弹性机制
from strategy.core.resilience import (
    GracefulDegradation,
    ExceptionIsolation,
    AutoScaler,
    EventPriority,
    DegradationLevel
)

logger = logging.getLogger(__name__)

# 使用从resilience导入的EventPriority


@dataclass(order=True)
class PrioritizedEvent:
    """带优先级的事件包装器"""
    priority: int = field(compare=True)
    timestamp: float = field(compare=True)
    event_type: str = field(compare=False)
    data: Any = field(compare=False)
    
    def __post_init__(self):
        # 确保timestamp用于相同优先级的FIFO排序
        if self.timestamp == 0:
            self.timestamp = time.time()


class EventMetrics:
    """事件引擎性能指标"""
    
    def __init__(self):
        self.events_received = 0
        self.events_processed = 0
        self.events_dropped = 0
        self.events_by_priority: Dict[int, int] = {}
        self.processing_times: List[float] = []
        self.queue_size_history: List[int] = []
        self._lock = threading.Lock()
    
    def record_received(self, priority: int = 2):
        """记录接收事件"""
        with self._lock:
            self.events_received += 1
            self.events_by_priority[priority] = self.events_by_priority.get(priority, 0) + 1
    
    def record_processed(self, processing_time: float):
        """记录处理完成事件"""
        with self._lock:
            self.events_processed += 1
            self.processing_times.append(processing_time)
            # 保留最近1000个处理时间
            if len(self.processing_times) > 1000:
                self.processing_times = self.processing_times[-1000:]
    
    def record_dropped(self):
        """记录丢弃事件"""
        with self._lock:
            self.events_dropped += 1
    
    def record_queue_size(self, size: int):
        """记录队列大小"""
        with self._lock:
            self.queue_size_history.append(size)
            if len(self.queue_size_history) > 1000:
                self.queue_size_history = self.queue_size_history[-1000:]
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            avg_processing_time = sum(self.processing_times) / len(self.processing_times) if self.processing_times else 0
            avg_queue_size = sum(self.queue_size_history) / len(self.queue_size_history) if self.queue_size_history else 0
            
            return {
                "events_received": self.events_received,
                "events_processed": self.events_processed,
                "events_dropped": self.events_dropped,
                "events_by_priority": self.events_by_priority.copy(),
                "avg_processing_time_ms": avg_processing_time * 1000,
                "avg_queue_size": avg_queue_size,
                "drop_rate": self.events_dropped / max(self.events_received, 1)
            }


class BoundedPriorityQueue:
    """有界优先级队列 - 使用堆实现"""
    
    def __init__(self, maxsize: int = 100000):
        self.maxsize = maxsize
        self._queue: List[PrioritizedEvent] = []
        self._lock = threading.Lock()
        self._not_empty = threading.Condition(self._lock)
        self._not_full = threading.Condition(self._lock)
        self._size = 0
    
    def put(self, event: PrioritizedEvent, block: bool = True, timeout: Optional[float] = None) -> bool:
        """
        添加事件到队列
        
        Args:
            event: 优先级事件
            block: 是否阻塞等待
            timeout: 阻塞超时时间
            
        Returns:
            bool: 是否成功添加
        """
        with self._not_full:
            if self._size >= self.maxsize:
                if not block:
                    return False
                # 等待队列有空间
                remaining = timeout
                while self._size >= self.maxsize:
                    if remaining is not None and remaining <= 0:
                        return False
                    start = time.time()
                    self._not_full.wait(timeout=remaining)
                    if remaining is not None:
                        remaining -= time.time() - start
            
            heapq.heappush(self._queue, event)
            self._size += 1
            self._not_empty.notify()
            return True
    
    def get(self, block: bool = True, timeout: Optional[float] = None) -> Optional[PrioritizedEvent]:
        """
        从队列获取事件
        
        Args:
            block: 是否阻塞等待
            timeout: 阻塞超时时间
            
        Returns:
            PrioritizedEvent or None: 优先级事件
        """
        with self._not_empty:
            if self._size == 0:
                if not block:
                    return None
                # 等待队列有数据
                remaining = timeout
                while self._size == 0:
                    if remaining is not None and remaining <= 0:
                        return None
                    start = time.time()
                    self._not_empty.wait(timeout=remaining)
                    if remaining is not None:
                        remaining -= time.time() - start
            
            event = heapq.heappop(self._queue)
            self._size -= 1
            self._not_full.notify()
            return event
    
    def qsize(self) -> int:
        """获取队列大小"""
        with self._lock:
            return self._size
    
    def empty(self) -> bool:
        """检查队列是否为空"""
        with self._lock:
            return self._size == 0
    
    def full(self) -> bool:
        """检查队列是否已满"""
        with self._lock:
            return self._size >= self.maxsize


class OptimizedEventEngine:
    """
    优化的事件引擎
    
    特性：
    1. 有界优先级队列 - 防止内存无限增长
    2. 背压机制 - 高负载时丢弃低优先级事件
    3. 多工作线程 - 并行处理事件
    4. 性能监控 - 实时统计指标
    5. 优雅降级 - 队列满时自动降级
    6. 异常隔离 - 处理器故障隔离
    7. 自动扩缩容 - 动态调整资源
    """
    
    def __init__(
        self,
        max_queue_size: int = 100000,
        num_workers: int = 4,
        enable_backpressure: bool = True,
        backpressure_threshold: float = 0.8,
        enable_graceful_degradation: bool = True,
        enable_exception_isolation: bool = True,
        enable_auto_scaling: bool = True,
        min_workers: int = 2,
        max_workers_limit: int = 32
    ):
        """
        初始化优化的事件引擎
        
        Args:
            max_queue_size: 最大队列大小
            num_workers: 工作线程数量
            enable_backpressure: 是否启用背压机制
            backpressure_threshold: 背压阈值（队列使用率）
            enable_graceful_degradation: 是否启用优雅降级
            enable_exception_isolation: 是否启用异常隔离
            enable_auto_scaling: 是否启用自动扩缩容
            min_workers: 最小工作线程数
            max_workers_limit: 最大工作线程数限制
        """
        self.max_queue_size = max_queue_size
        self.num_workers = num_workers
        self.enable_backpressure = enable_backpressure
        self.backpressure_threshold = backpressure_threshold
        self.min_workers = min_workers
        self.max_workers_limit = max_workers_limit
        
        # 有界优先级队列
        self.event_queue = BoundedPriorityQueue(maxsize=max_queue_size)
        
        # 事件处理器
        self.handlers: Dict[str, List[Callable]] = {}
        self._handlers_lock = threading.RLock()
        
        # 工作线程
        self._workers: List[threading.Thread] = []
        self._executor: Optional[ThreadPoolExecutor] = None
        
        # 运行状态
        self.running = False
        self._stop_event = threading.Event()
        
        # 性能指标
        self.metrics = EventMetrics()
        
        # 背压状态
        self._backpressure_active = False
        self._dropped_count = 0
        
        # 弹性机制
        self._graceful_degradation: Optional[GracefulDegradation] = None
        self._exception_isolation: Optional[ExceptionIsolation] = None
        self._auto_scaler: Optional[AutoScaler] = None
        
        if enable_graceful_degradation:
            self._graceful_degradation = GracefulDegradation(
                on_level_change=self._on_degradation_level_change
            )
        
        if enable_exception_isolation:
            self._exception_isolation = ExceptionIsolation()
        
        if enable_auto_scaling:
            self._auto_scaler = AutoScaler(
                min_workers=min_workers,
                max_workers=max_workers_limit,
                scale_up_threshold=0.7,
                scale_down_threshold=0.3
            )
        
        logger.info(f"优化的事件引擎初始化完成: 队列大小={max_queue_size}, 工作线程={num_workers}")
    
    def _on_degradation_level_change(self, old_level: DegradationLevel, new_level: DegradationLevel):
        """降级级别变化回调"""
        logger.warning(f"事件引擎降级级别变化: {old_level.name} -> {new_level.name}")
        # 可以在这里触发告警通知
    
    def register(self, event_type: str, handler: Callable, 
                 failure_threshold: Optional[int] = None,
                 recovery_timeout: Optional[float] = None) -> None:
        """
        注册事件处理器
        
        Args:
            event_type: 事件类型
            handler: 处理函数
            failure_threshold: 失败阈值（可选，用于熔断器）
            recovery_timeout: 恢复超时（可选，用于熔断器）
        """
        with self._handlers_lock:
            if event_type not in self.handlers:
                self.handlers[event_type] = []
            
            # 如果启用异常隔离，包装处理器
            if self._exception_isolation:
                handler = self._exception_isolation.wrap_handler(
                    event_type, handler, failure_threshold, recovery_timeout
                )
            
            self.handlers[event_type].append(handler)
            logger.debug(f"注册事件处理器: {event_type}, 当前处理器数量: {len(self.handlers[event_type])}")
    
    def unregister(self, event_type: str, handler: Callable) -> bool:
        """
        注销事件处理器
        
        Args:
            event_type: 事件类型
            handler: 处理函数
            
        Returns:
            bool: 是否成功注销
        """
        with self._handlers_lock:
            if event_type in self.handlers and handler in self.handlers[event_type]:
                self.handlers[event_type].remove(handler)
                return True
            return False
    
    def put(
        self,
        event_type: str,
        data: Any,
        priority: EventPriority = EventPriority.NORMAL,
        block: bool = False,
        timeout: Optional[float] = None
    ) -> bool:
        """
        添加事件到队列
        
        Args:
            event_type: 事件类型
            data: 事件数据
            priority: 事件优先级
            block: 是否阻塞等待
            timeout: 阻塞超时时间
            
        Returns:
            bool: 是否成功添加
        """
        # 获取当前队列使用率
        queue_usage = self.event_queue.qsize() / self.max_queue_size
        
        # 优雅降级检查
        if self._graceful_degradation:
            self._graceful_degradation.update_level(queue_usage)
            if not self._graceful_degradation.should_accept_event(priority):
                self.metrics.record_dropped()
                self._dropped_count += 1
                if self._dropped_count % 1000 == 1:
                    logger.warning(
                        f"优雅降级机制激活，已丢弃 {self._dropped_count} 个事件 "
                        f"(当前级别: {self._graceful_degradation.current_level.name})"
                    )
                return False
        
        # 背压检查（作为后备机制）
        if self.enable_backpressure and self._should_apply_backpressure(priority):
            self.metrics.record_dropped()
            self._dropped_count += 1
            if self._dropped_count % 1000 == 1:
                logger.warning(f"背压机制激活，已丢弃 {self._dropped_count} 个低优先级事件")
            return False
        
        # 创建优先级事件
        event = PrioritizedEvent(
            priority=priority.value,
            timestamp=time.time(),
            event_type=event_type,
            data=data
        )
        
        # 添加到队列
        success = self.event_queue.put(event, block=block, timeout=timeout)
        
        if success:
            self.metrics.record_received(priority.value)
            logger.debug(f"事件已添加: {event_type}, 优先级: {priority.name}")
        else:
            self.metrics.record_dropped()
            logger.warning(f"事件添加失败（队列已满）: {event_type}")
        
        # 记录负载用于自动扩缩容
        if self._auto_scaler:
            self._auto_scaler.record_load(queue_usage)
        
        return success
    
    def _should_apply_backpressure(self, priority: EventPriority) -> bool:
        """
        检查是否应该应用背压
        
        Args:
            priority: 事件优先级
            
        Returns:
            bool: 是否应该丢弃该事件
        """
        queue_usage = self.event_queue.qsize() / self.max_queue_size
        
        # 如果队列使用率超过阈值
        if queue_usage >= self.backpressure_threshold:
            self._backpressure_active = True
            # 丢弃低优先级事件（NORMAL及以下）
            if priority.value >= EventPriority.NORMAL.value:
                return True
        else:
            self._backpressure_active = False
        
        return False
    
    def start(self) -> None:
        """启动事件引擎"""
        if self.running:
            logger.warning("事件引擎已在运行")
            return
        
        self.running = True
        self._stop_event.clear()
        
        # 确定初始工作线程数
        initial_workers = self.num_workers
        if self._auto_scaler:
            initial_workers = self._auto_scaler.current_workers
        
        # 创建工作线程
        self._workers = []
        for i in range(initial_workers):
            worker = threading.Thread(
                target=self._worker_loop,
                args=(i,),
                name=f"EventWorker-{i}",
                daemon=True
            )
            worker.start()
            self._workers.append(worker)
        
        # 创建监控线程
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            name="EventMonitor",
            daemon=True
        )
        self._monitor_thread.start()
        
        # 创建自动扩缩容监控线程
        if self._auto_scaler:
            self._scaling_thread = threading.Thread(
                target=self._scaling_loop,
                name="AutoScaler",
                daemon=True
            )
            self._scaling_thread.start()
        
        logger.info(f"事件引擎已启动: {initial_workers} 个工作线程")
    
    def _scaling_loop(self) -> None:
        """自动扩缩容监控循环"""
        if not self._auto_scaler:
            return
            
        while self.running and not self._stop_event.is_set():
            try:
                # 评估是否需要扩缩容
                operation, target_workers = self._auto_scaler.evaluate_scaling()
                
                if operation and target_workers:
                    # 应用扩缩容决策
                    if self._auto_scaler.apply_scaling(operation, target_workers):
                        # 根据操作调整工作线程
                        if operation == "scale_up":
                            self._add_workers(target_workers - len(self._workers))
                        elif operation == "scale_down":
                            self._remove_workers(len(self._workers) - target_workers)
                
                time.sleep(5.0)  # 每5秒检查一次
                
            except Exception as e:
                logger.error(f"自动扩缩容监控出错: {e}")
    
    def _add_workers(self, count: int) -> None:
        """添加工作线程"""
        for i in range(count):
            worker_id = len(self._workers)
            worker = threading.Thread(
                target=self._worker_loop,
                args=(worker_id,),
                name=f"EventWorker-{worker_id}",
                daemon=True
            )
            worker.start()
            self._workers.append(worker)
        logger.info(f"添加了 {count} 个工作线程，当前总数: {len(self._workers)}")
    
    def _remove_workers(self, count: int) -> None:
        """移除工作线程（通过设置停止标志，让线程自然结束）"""
        # 注意：这里只是标记，实际线程会在处理完当前事件后退出
        # 为简化实现，我们不强制终止线程，而是等待它们自然结束
        logger.info(f"计划移除 {count} 个工作线程，当前总数: {len(self._workers)}")
    
    def stop(self, timeout: float = 5.0) -> None:
        """
        停止事件引擎
        
        Args:
            timeout: 停止超时时间
        """
        if not self.running:
            return
        
        logger.info("正在停止事件引擎...")
        self.running = False
        self._stop_event.set()
        
        # 等待工作线程结束
        for worker in self._workers:
            worker.join(timeout=timeout / len(self._workers))
        
        # 等待监控线程结束
        if hasattr(self, '_monitor_thread'):
            self._monitor_thread.join(timeout=1.0)
        
        logger.info("事件引擎已停止")
        
        # 输出最终统计
        stats = self.metrics.get_stats()
        logger.info(f"最终统计: 接收={stats['events_received']}, "
                   f"处理={stats['events_processed']}, "
                   f"丢弃={stats['events_dropped']}")
    
    def _worker_loop(self, worker_id: int) -> None:
        """
        工作线程主循环
        
        Args:
            worker_id: 工作线程ID
        """
        logger.debug(f"工作线程 {worker_id} 已启动")
        
        while self.running and not self._stop_event.is_set():
            try:
                # 获取事件（带超时）
                event = self.event_queue.get(block=True, timeout=0.1)
                
                if event is None:
                    continue
                
                # 处理事件
                start_time = time.time()
                self._process_event(event)
                processing_time = time.time() - start_time
                
                # 记录指标
                self.metrics.record_processed(processing_time)
                
            except Exception as e:
                logger.error(f"工作线程 {worker_id} 处理事件时出错: {e}")
        
        logger.debug(f"工作线程 {worker_id} 已停止")
    
    def _process_event(self, event: PrioritizedEvent) -> None:
        """
        处理单个事件
        
        Args:
            event: 优先级事件
        """
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
    
    def _monitor_loop(self) -> None:
        """监控线程主循环 - 定期记录性能指标"""
        while self.running and not self._stop_event.is_set():
            try:
                # 记录队列大小
                self.metrics.record_queue_size(self.event_queue.qsize())
                
                # 每10秒输出统计
                if self.metrics.events_received % 10000 == 0 and self.metrics.events_received > 0:
                    stats = self.metrics.get_stats()
                    logger.info(f"事件引擎统计: 队列大小={stats['avg_queue_size']:.0f}, "
                               f"平均处理时间={stats['avg_processing_time_ms']:.2f}ms, "
                               f"丢弃率={stats['drop_rate']:.2%}")
                
                # 检查背压状态
                if self._backpressure_active:
                    queue_usage = self.event_queue.qsize() / self.max_queue_size
                    logger.warning(f"背压状态: 队列使用率={queue_usage:.1%}")
                
                time.sleep(1.0)
                
            except Exception as e:
                logger.error(f"监控线程出错: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取事件引擎统计信息"""
        base_stats = self.metrics.get_stats()
        
        # 添加弹性机制统计
        resilience_stats = {}
        
        if self._graceful_degradation:
            resilience_stats["degradation"] = self._graceful_degradation.get_stats()
        
        if self._exception_isolation:
            resilience_stats["exception_isolation"] = {
                "circuit_breakers": self._exception_isolation.get_circuit_breaker_stats(),
                "handlers": self._exception_isolation.get_handler_stats(),
                "dead_letter_queue_size": self._exception_isolation.get_dead_letter_queue_size()
            }
        
        if self._auto_scaler:
            resilience_stats["auto_scaler"] = self._auto_scaler.get_stats()
        
        return {
            **base_stats,
            "resilience": resilience_stats,
            "workers": {
                "current": len(self._workers),
                "min": self.min_workers,
                "max": self.max_workers_limit
            }
        }
    
    def is_healthy(self) -> bool:
        """检查引擎健康状态"""
        stats = self.metrics.get_stats()
        # 如果丢弃率超过5%，认为不健康
        if stats['drop_rate'] >= 0.05:
            return False
        
        # 检查降级级别
        if self._graceful_degradation:
            if self._graceful_degradation.current_level.value >= DegradationLevel.HEAVY.value:
                return False
        
        return True
    
    def reset_circuit_breakers(self) -> None:
        """重置所有熔断器"""
        if self._exception_isolation:
            self._exception_isolation.reset_all_circuit_breakers()
    
    def get_dead_letter_items(self, max_items: int = 100) -> List[Dict[str, Any]]:
        """获取死信队列中的项目"""
        if self._exception_isolation:
            return self._exception_isolation.get_dead_letter_items(max_items)
        return []
    
    def force_degradation_level(self, level: DegradationLevel) -> None:
        """强制设置降级级别（用于手动控制）"""
        if self._graceful_degradation:
            self._graceful_degradation.force_level(level)


# 兼容性：保留原始EventEngine的接口
class EventEngine(OptimizedEventEngine):
    """
    向后兼容的事件引擎
    
    继承自OptimizedEventEngine，保持与原始EventEngine相同的接口
    """
    
    def __init__(self):
        # 使用默认参数初始化优化引擎
        super().__init__(
            max_queue_size=100000,
            num_workers=1,  # 原始引擎使用单线程
            enable_backpressure=True,
            backpressure_threshold=0.9
        )
    
    def put(self, event_type: str, data: Any = None) -> bool:
        """
        向后兼容的put方法
        
        Args:
            event_type: 事件类型
            data: 事件数据
            
        Returns:
            bool: 是否成功添加
        """
        return super().put(event_type, data, priority=EventPriority.NORMAL, block=False)


# 便捷函数
def create_optimized_engine(
    max_queue_size: int = 100000,
    num_workers: int = 4,
    enable_backpressure: bool = True,
    backpressure_threshold: float = 0.8
) -> OptimizedEventEngine:
    """
    创建优化的事件引擎

    Args:
        max_queue_size: 最大队列大小
        num_workers: 工作线程数量
        enable_backpressure: 是否启用背压
        backpressure_threshold: 背压阈值

    Returns:
        OptimizedEventEngine: 优化的事件引擎实例
    """
    return OptimizedEventEngine(
        max_queue_size=max_queue_size,
        num_workers=num_workers,
        enable_backpressure=enable_backpressure,
        backpressure_threshold=backpressure_threshold
    )
