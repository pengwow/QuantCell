"""
事件引擎弹性机制 - 边界情况处理

提供以下功能：
1. 优雅降级机制 (GracefulDegradation) - 队列满时自动降级
2. 异常隔离框架 (ExceptionIsolation) - 处理器故障隔离
3. 熔断器模式 (CircuitBreaker) - 防止级联故障
4. 自动扩缩容 (AutoScaler) - 动态调整资源
"""

import threading
import time
import logging
from typing import Dict, List, Callable, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import IntEnum
from queue import Queue, Empty
from collections import deque

logger = logging.getLogger(__name__)


class EventPriority(IntEnum):
    """事件优先级定义"""
    CRITICAL = 0    # 关键事件：止损、强制平仓
    HIGH = 1        # 高优先级：止盈、风控
    NORMAL = 2      # 正常优先级：常规交易信号
    LOW = 3         # 低优先级：日志、统计
    BACKGROUND = 4  # 后台任务：数据持久化


class DegradationLevel(IntEnum):
    """降级级别"""
    NORMAL = 0      # 正常模式 - 所有事件正常处理
    LIGHT = 1       # 轻度降级 - 丢弃BACKGROUND优先级事件
    MEDIUM = 2      # 中度降级 - 丢弃LOW和BACKGROUND优先级事件
    HEAVY = 3       # 重度降级 - 只保留CRITICAL和HIGH优先级事件
    EMERGENCY = 4   # 紧急模式 - 只处理CRITICAL事件


@dataclass
class DegradationConfig:
    """降级配置"""
    level: DegradationLevel
    max_priority: int
    description: str
    queue_usage_threshold: float


class GracefulDegradation:
    """
    优雅降级机制
    
    当系统负载过高时，自动降低服务质量以保证核心功能可用。
    支持多级降级策略，根据队列使用率自动调整降级级别。
    """
    
    # 降级级别配置
    LEVELS = {
        DegradationLevel.NORMAL: DegradationConfig(
            level=DegradationLevel.NORMAL,
            max_priority=4,
            description="正常模式 - 所有事件正常处理",
            queue_usage_threshold=0.0
        ),
        DegradationLevel.LIGHT: DegradationConfig(
            level=DegradationLevel.LIGHT,
            max_priority=3,
            description="轻度降级 - 丢弃BACKGROUND优先级事件",
            queue_usage_threshold=0.80
        ),
        DegradationLevel.MEDIUM: DegradationConfig(
            level=DegradationLevel.MEDIUM,
            max_priority=2,
            description="中度降级 - 丢弃LOW和BACKGROUND优先级事件",
            queue_usage_threshold=0.94
        ),
        DegradationLevel.HEAVY: DegradationConfig(
            level=DegradationLevel.HEAVY,
            max_priority=1,
            description="重度降级 - 只保留CRITICAL和HIGH优先级事件",
            queue_usage_threshold=0.95
        ),
        DegradationLevel.EMERGENCY: DegradationConfig(
            level=DegradationLevel.EMERGENCY,
            max_priority=0,
            description="紧急模式 - 只处理CRITICAL事件",
            queue_usage_threshold=0.99
        )
    }
    
    # 恢复阈值（比降级阈值低，防止震荡）
    RECOVERY_THRESHOLD_OFFSET = 0.15
    
    def __init__(
        self,
        enable_auto_recovery: bool = True,
        recovery_check_interval: float = 5.0,
        on_level_change: Optional[Callable[[DegradationLevel, DegradationLevel], None]] = None
    ):
        """
        初始化优雅降级机制
        
        Args:
            enable_auto_recovery: 是否启用自动恢复
            recovery_check_interval: 恢复检查间隔（秒）
            on_level_change: 降级级别变化回调函数
        """
        self._current_level = DegradationLevel.NORMAL
        self._enable_auto_recovery = enable_auto_recovery
        self._recovery_check_interval = recovery_check_interval
        self._on_level_change = on_level_change
        
        self._lock = threading.RLock()
        self._level_change_count = 0
        self._last_level_change_time = time.time()
        self._events_dropped_by_level: Dict[DegradationLevel, int] = {
            level: 0 for level in DegradationLevel
        }
        
        logger.info("优雅降级机制初始化完成")
    
    @property
    def current_level(self) -> DegradationLevel:
        """获取当前降级级别"""
        with self._lock:
            return self._current_level
    
    @property
    def current_config(self) -> DegradationConfig:
        """获取当前降级配置"""
        return self.LEVELS[self.current_level]
    
    def should_accept_event(self, priority: EventPriority) -> bool:
        """
        检查是否应该接受事件
        
        Args:
            priority: 事件优先级
            
        Returns:
            bool: 是否接受该事件
        """
        config = self.current_config
        should_accept = priority.value <= config.max_priority
        
        if not should_accept:
            with self._lock:
                self._events_dropped_by_level[self._current_level] += 1
        
        return should_accept
    
    def update_level(self, queue_usage: float) -> Optional[DegradationLevel]:
        """
        根据队列使用率更新降级级别
        
        Args:
            queue_usage: 队列使用率 (0.0 - 1.0)
            
        Returns:
            Optional[DegradationLevel]: 如果级别发生变化，返回新级别，否则返回None
        """
        with self._lock:
            old_level = self._current_level
            new_level = self._determine_level(queue_usage)
            
            if new_level != old_level:
                self._current_level = new_level
                self._level_change_count += 1
                self._last_level_change_time = time.time()
                
                logger.warning(
                    f"降级级别变化: {old_level.name} -> {new_level.name} "
                    f"(队列使用率: {queue_usage:.1%}, "
                    f"配置: {self.LEVELS[new_level].description})"
                )
                
                # 触发回调
                if self._on_level_change:
                    try:
                        self._on_level_change(old_level, new_level)
                    except Exception as e:
                        logger.error(f"降级级别变化回调执行失败: {e}")
                
                return new_level
            
            return None
    
    def _determine_level(self, queue_usage: float) -> DegradationLevel:
        """
        根据队列使用率确定降级级别

        使用带有恢复阈值的策略，防止级别在边界震荡
        """
        current = self._current_level

        # 检查是否需要升级（更严格的降级）
        # 只能逐级升级
        next_level_value = current.value + 1
        if next_level_value <= 4:  # 最大是EMERGENCY=4
            next_level = DegradationLevel(next_level_value)
            if next_level in self.LEVELS:
                if queue_usage >= self.LEVELS[next_level].queue_usage_threshold:
                    return next_level

        # 检查是否可以降级（恢复）
        if self._enable_auto_recovery and current != DegradationLevel.NORMAL:
            # 计算恢复阈值
            recovery_threshold = self.LEVELS[current].queue_usage_threshold - self.RECOVERY_THRESHOLD_OFFSET

            if queue_usage < recovery_threshold:
                # 可以降级一级
                prev_level = DegradationLevel(current.value - 1)
                logger.info(
                    f"降级级别恢复: {current.name} -> {prev_level.name} "
                    f"(队列使用率: {queue_usage:.1%} < 恢复阈值: {recovery_threshold:.1%})"
                )
                return prev_level

        return current
    
    def force_level(self, level: DegradationLevel) -> None:
        """
        强制设置降级级别（用于手动控制）
        
        Args:
            level: 目标降级级别
        """
        with self._lock:
            old_level = self._current_level
            if old_level != level:
                self._current_level = level
                self._level_change_count += 1
                self._last_level_change_time = time.time()
                
                logger.warning(f"强制降级级别变化: {old_level.name} -> {level.name}")
                
                if self._on_level_change:
                    try:
                        self._on_level_change(old_level, level)
                    except Exception as e:
                        logger.error(f"降级级别变化回调执行失败: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取降级机制统计信息"""
        with self._lock:
            return {
                "current_level": self._current_level.name,
                "current_description": self.current_config.description,
                "level_change_count": self._level_change_count,
                "last_level_change_time": self._last_level_change_time,
                "time_since_last_change_sec": time.time() - self._last_level_change_time,
                "events_dropped_by_level": {
                    level.name: count 
                    for level, count in self._events_dropped_by_level.items()
                },
                "total_events_dropped": sum(self._events_dropped_by_level.values())
            }
    
    def reset(self) -> None:
        """重置降级机制到正常状态"""
        with self._lock:
            self._current_level = DegradationLevel.NORMAL
            self._level_change_count = 0
            self._last_level_change_time = time.time()
            self._events_dropped_by_level = {
                level: 0 for level in DegradationLevel
            }
            logger.info("降级机制已重置到正常状态")


class CircuitBreakerState(IntEnum):
    """熔断器状态"""
    CLOSED = 0      # 关闭状态 - 正常执行
    OPEN = 1        # 打开状态 - 拒绝执行
    HALF_OPEN = 2   # 半开状态 - 尝试恢复


class CircuitBreaker:
    """
    熔断器模式实现
    
    防止故障处理器反复执行导致系统资源浪费。
    当连续失败次数超过阈值时，熔断器打开，暂时拒绝执行。
    经过恢复超时后，进入半开状态，尝试恢复执行。
    """
    
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_max_calls: int = 3,
        success_threshold: int = 2
    ):
        """
        初始化熔断器
        
        Args:
            name: 熔断器名称（用于日志）
            failure_threshold: 失败阈值，超过此值熔断器打开
            recovery_timeout: 恢复超时时间（秒）
            half_open_max_calls: 半开状态最大尝试次数
            success_threshold: 半开状态成功阈值，超过此值熔断器关闭
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self.success_threshold = success_threshold
        
        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0
        self._last_failure_time = 0.0
        
        self._lock = threading.RLock()
        
        # 统计
        self._total_failures = 0
        self._total_successes = 0
        self._state_changes = 0
        
        logger.debug(f"熔断器 '{name}' 初始化完成")
    
    @property
    def state(self) -> CircuitBreakerState:
        """获取当前状态"""
        with self._lock:
            return self._state
    
    def can_execute(self) -> bool:
        """
        检查是否可以执行
        
        Returns:
            bool: 是否可以执行
        """
        with self._lock:
            if self._state == CircuitBreakerState.CLOSED:
                return True
            
            elif self._state == CircuitBreakerState.OPEN:
                # 检查是否超过恢复超时
                if time.time() - self._last_failure_time >= self.recovery_timeout:
                    self._state = CircuitBreakerState.HALF_OPEN
                    self._half_open_calls = 0
                    self._success_count = 0
                    self._state_changes += 1
                    logger.info(f"熔断器 '{self.name}' 进入半开状态")
                    # 进入半开状态后，检查是否可以执行
                    if self._half_open_calls < self.half_open_max_calls:
                        self._half_open_calls += 1
                        return True
                    else:
                        return False
                else:
                    return False
            
            elif self._state == CircuitBreakerState.HALF_OPEN:
                # 限制半开状态的尝试次数
                if self._half_open_calls < self.half_open_max_calls:
                    self._half_open_calls += 1
                    return True
                else:
                    return False
            
            return False
    
    def record_success(self) -> None:
        """记录成功执行"""
        with self._lock:
            self._total_successes += 1
            
            if self._state == CircuitBreakerState.HALF_OPEN:
                self._success_count += 1
                
                # 检查是否可以关闭熔断器
                if self._success_count >= self.success_threshold:
                    self._state = CircuitBreakerState.CLOSED
                    self._failure_count = 0
                    self._half_open_calls = 0
                    self._state_changes += 1
                    logger.info(f"熔断器 '{self.name}' 关闭 - 服务已恢复")
            
            elif self._state == CircuitBreakerState.CLOSED:
                # 重置失败计数
                if self._failure_count > 0:
                    self._failure_count = 0
    
    def record_failure(self) -> None:
        """记录失败执行"""
        with self._lock:
            self._total_failures += 1
            self._failure_count += 1
            self._last_failure_time = time.time()
            
            if self._state == CircuitBreakerState.HALF_OPEN:
                # 半开状态失败，重新打开熔断器
                self._state = CircuitBreakerState.OPEN
                self._state_changes += 1
                logger.warning(
                    f"熔断器 '{self.name}' 重新打开 - 半开状态恢复失败 "
                    f"(失败次数: {self._failure_count})"
                )
            
            elif self._state == CircuitBreakerState.CLOSED:
                # 检查是否超过失败阈值
                if self._failure_count >= self.failure_threshold:
                    self._state = CircuitBreakerState.OPEN
                    self._state_changes += 1
                    logger.error(
                        f"熔断器 '{self.name}' 打开 - 连续失败 {self._failure_count} 次，"
                        f"将在 {self.recovery_timeout} 秒后尝试恢复"
                    )
    
    def get_stats(self) -> Dict[str, Any]:
        """获取熔断器统计信息"""
        with self._lock:
            return {
                "name": self.name,
                "state": self._state.name,
                "failure_count": self._failure_count,
                "success_count": self._success_count,
                "half_open_calls": self._half_open_calls,
                "last_failure_time": self._last_failure_time,
                "time_since_last_failure": time.time() - self._last_failure_time,
                "total_failures": self._total_failures,
                "total_successes": self._total_successes,
                "state_changes": self._state_changes
            }
    
    def reset(self) -> None:
        """重置熔断器到初始状态"""
        with self._lock:
            self._state = CircuitBreakerState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._half_open_calls = 0
            self._last_failure_time = 0.0
            logger.info(f"熔断器 '{self.name}' 已重置")


class ExceptionIsolation:
    """
    异常隔离框架
    
    提供处理器级别的异常隔离，包括：
    1. 异常捕获和日志记录
    2. 熔断器保护
    3. 死信队列
    4. 处理器健康检查
    """
    
    def __init__(
        self,
        enable_circuit_breaker: bool = True,
        enable_dead_letter_queue: bool = True,
        dead_letter_queue_size: int = 10000,
        default_failure_threshold: int = 5,
        default_recovery_timeout: float = 60.0
    ):
        """
        初始化异常隔离框架
        
        Args:
            enable_circuit_breaker: 是否启用熔断器
            enable_dead_letter_queue: 是否启用死信队列
            dead_letter_queue_size: 死信队列大小
            default_failure_threshold: 默认失败阈值
            default_recovery_timeout: 默认恢复超时
        """
        self._enable_circuit_breaker = enable_circuit_breaker
        self._enable_dead_letter_queue = enable_dead_letter_queue
        
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        self._default_failure_threshold = default_failure_threshold
        self._default_recovery_timeout = default_recovery_timeout
        
        self._dead_letter_queue: Optional[Queue] = None
        if enable_dead_letter_queue:
            self._dead_letter_queue = Queue(maxsize=dead_letter_queue_size)
        
        self._handler_stats: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
        
        logger.info("异常隔离框架初始化完成")
    
    def wrap_handler(
        self,
        event_type: str,
        handler: Callable,
        failure_threshold: Optional[int] = None,
        recovery_timeout: Optional[float] = None
    ) -> Callable:
        """
        包装处理器，添加异常隔离
        
        Args:
            event_type: 事件类型
            handler: 原始处理器函数
            failure_threshold: 失败阈值（可选）
            recovery_timeout: 恢复超时（可选）
            
        Returns:
            Callable: 包装后的处理器函数
        """
        handler_id = f"{event_type}_{id(handler)}"
        
        # 创建熔断器
        if self._enable_circuit_breaker:
            cb_name = f"{event_type}_{handler.__name__ if hasattr(handler, '__name__') else 'anonymous'}"
            self._circuit_breakers[handler_id] = CircuitBreaker(
                name=cb_name,
                failure_threshold=failure_threshold or self._default_failure_threshold,
                recovery_timeout=recovery_timeout or self._default_recovery_timeout
            )
        
        # 初始化统计
        with self._lock:
            self._handler_stats[handler_id] = {
                "event_type": event_type,
                "handler_name": handler.__name__ if hasattr(handler, '__name__') else 'anonymous',
                "total_calls": 0,
                "total_successes": 0,
                "total_failures": 0,
                "total_exceptions": 0,
                "avg_execution_time_ms": 0.0,
                "execution_times": deque(maxlen=100)
            }
        
        def wrapped_handler(data: Any) -> bool:
            """包装后的处理器"""
            handler_id_inner = handler_id
            stats = self._handler_stats[handler_id_inner]
            
            # 检查熔断器
            if self._enable_circuit_breaker:
                cb = self._circuit_breakers.get(handler_id_inner)
                if cb and not cb.can_execute():
                    logger.debug(f"熔断器阻止执行: {cb.name}")
                    return False
            
            start_time = time.time()
            success = False
            
            try:
                stats["total_calls"] += 1
                
                # 执行处理器
                result = handler(data)
                success = True
                
                # 记录成功
                stats["total_successes"] += 1
                if self._enable_circuit_breaker and cb:
                    cb.record_success()
                
                return result if isinstance(result, bool) else True
                
            except Exception as e:
                # 记录异常
                stats["total_failures"] += 1
                stats["total_exceptions"] += 1
                
                logger.error(
                    f"处理器执行异常: event_type={event_type}, "
                    f"handler={stats['handler_name']}, error={e}",
                    exc_info=True
                )
                
                # 记录到熔断器
                if self._enable_circuit_breaker and cb:
                    cb.record_failure()
                
                # 添加到死信队列
                if self._enable_dead_letter_queue and self._dead_letter_queue:
                    try:
                        self._dead_letter_queue.put_nowait({
                            "event_type": event_type,
                            "data": data,
                            "error": str(e),
                            "timestamp": time.time(),
                            "handler_id": handler_id_inner
                        })
                    except:
                        pass  # 死信队列满，忽略
                
                return False
                
            finally:
                # 记录执行时间
                execution_time = time.time() - start_time
                stats["execution_times"].append(execution_time)
                stats["avg_execution_time_ms"] = (
                    sum(stats["execution_times"]) / len(stats["execution_times"]) * 1000
                )
        
        # 保存原始处理器引用
        wrapped_handler._original_handler = handler
        wrapped_handler._handler_id = handler_id
        
        return wrapped_handler
    
    def get_circuit_breaker_stats(self) -> Dict[str, Dict[str, Any]]:
        """获取所有熔断器统计信息"""
        return {
            name: cb.get_stats()
            for name, cb in self._circuit_breakers.items()
        }
    
    def get_handler_stats(self) -> Dict[str, Dict[str, Any]]:
        """获取所有处理器统计信息"""
        with self._lock:
            return {
                handler_id: {
                    "event_type": stats["event_type"],
                    "handler_name": stats["handler_name"],
                    "total_calls": stats["total_calls"],
                    "total_successes": stats["total_successes"],
                    "total_failures": stats["total_failures"],
                    "success_rate": (
                        stats["total_successes"] / stats["total_calls"]
                        if stats["total_calls"] > 0 else 0.0
                    ),
                    "avg_execution_time_ms": stats["avg_execution_time_ms"]
                }
                for handler_id, stats in self._handler_stats.items()
            }
    
    def get_dead_letter_queue_size(self) -> int:
        """获取死信队列大小"""
        if self._dead_letter_queue:
            return self._dead_letter_queue.qsize()
        return 0
    
    def get_dead_letter_items(self, max_items: int = 100) -> List[Dict[str, Any]]:
        """
        获取死信队列中的项目（非阻塞）
        
        Args:
            max_items: 最大获取数量
            
        Returns:
            List[Dict]: 死信项目列表
        """
        items = []
        if self._dead_letter_queue:
            for _ in range(min(max_items, self._dead_letter_queue.qsize())):
                try:
                    item = self._dead_letter_queue.get_nowait()
                    items.append(item)
                except Empty:
                    break
        return items
    
    def reset_circuit_breaker(self, handler_id: str) -> bool:
        """
        重置指定熔断器
        
        Args:
            handler_id: 处理器ID
            
        Returns:
            bool: 是否成功重置
        """
        if handler_id in self._circuit_breakers:
            self._circuit_breakers[handler_id].reset()
            return True
        return False
    
    def reset_all_circuit_breakers(self) -> None:
        """重置所有熔断器"""
        for cb in self._circuit_breakers.values():
            cb.reset()
        logger.info("所有熔断器已重置")


class AutoScaler:
    """
    自动扩缩容管理器
    
    根据系统负载自动调整工作线程数量，支持：
    1. 基于队列等待时间的扩容
    2. 基于处理延迟的扩容
    3. 基于CPU使用率的扩容
    4. 渐进式扩容和缩容
    5. 冷却期防止震荡
    """
    
    def __init__(
        self,
        min_workers: int = 2,
        max_workers: int = 32,
        scale_up_threshold: float = 0.7,
        scale_down_threshold: float = 0.3,
        scale_up_ratio: float = 0.25,
        scale_down_ratio: float = 0.15,
        cooldown_period: float = 60.0,
        evaluation_window: int = 10
    ):
        """
        初始化自动扩缩容管理器
        
        Args:
            min_workers: 最小工作线程数
            max_workers: 最大工作线程数
            scale_up_threshold: 扩容阈值（负载超过此值触发扩容）
            scale_down_threshold: 缩容阈值（负载低于此值触发缩容）
            scale_up_ratio: 扩容比例（每次增加当前数量的百分比）
            scale_down_ratio: 缩容比例（每次减少当前数量的百分比）
            cooldown_period: 冷却期（秒）
            evaluation_window: 评估窗口大小（样本数）
        """
        self.min_workers = min_workers
        self.max_workers = max_workers
        self.scale_up_threshold = scale_up_threshold
        self.scale_down_threshold = scale_down_threshold
        self.scale_up_ratio = scale_up_ratio
        self.scale_down_ratio = scale_down_ratio
        self.cooldown_period = cooldown_period
        self.evaluation_window = evaluation_window
        
        self._current_workers = min_workers
        self._last_scale_time = 0.0
        self._scale_history: List[Dict[str, Any]] = []
        
        # 负载历史
        self._load_history: deque = deque(maxlen=evaluation_window)
        
        self._lock = threading.RLock()
        
        logger.info(
            f"自动扩缩容管理器初始化完成: "
            f"min={min_workers}, max={max_workers}, "
            f"scale_up_threshold={scale_up_threshold}, "
            f"scale_down_threshold={scale_down_threshold}"
        )
    
    @property
    def current_workers(self) -> int:
        """获取当前工作线程数"""
        with self._lock:
            return self._current_workers
    
    def record_load(self, load_metric: float) -> None:
        """
        记录负载指标
        
        Args:
            load_metric: 负载指标 (0.0 - 1.0)
        """
        with self._lock:
            self._load_history.append(load_metric)
    
    def evaluate_scaling(self) -> Tuple[Optional[str], Optional[int]]:
        """
        评估是否需要扩缩容
        
        Returns:
            Tuple[Optional[str], Optional[int]]: (操作类型, 目标工作线程数)
            操作类型: "scale_up", "scale_down", 或 None
        """
        with self._lock:
            # 检查冷却期
            time_since_last_scale = time.time() - self._last_scale_time
            if time_since_last_scale < self.cooldown_period:
                return None, None
            
            # 需要足够的样本
            if len(self._load_history) < self.evaluation_window // 2:
                return None, None
            
            # 计算平均负载
            avg_load = sum(self._load_history) / len(self._load_history)
            
            # 检查扩容
            if avg_load >= self.scale_up_threshold:
                if self._current_workers < self.max_workers:
                    target = min(
                        max(int(self._current_workers * (1 + self.scale_up_ratio)), self._current_workers + 1),
                        self.max_workers
                    )
                    if target > self._current_workers:
                        return "scale_up", target
            
            # 检查缩容
            elif avg_load <= self.scale_down_threshold:
                if self._current_workers > self.min_workers:
                    target = max(
                        int(self._current_workers * (1 - self.scale_down_ratio)),
                        self.min_workers
                    )
                    if target < self._current_workers:
                        return "scale_down", target
            
            return None, None
    
    def apply_scaling(self, operation: str, target_workers: int) -> bool:
        """
        应用扩缩容决策
        
        Args:
            operation: 操作类型 ("scale_up" 或 "scale_down")
            target_workers: 目标工作线程数
            
        Returns:
            bool: 是否成功应用
        """
        with self._lock:
            old_workers = self._current_workers
            
            # 验证目标值
            target_workers = max(self.min_workers, min(self.max_workers, target_workers))
            
            if target_workers == old_workers:
                return False
            
            self._current_workers = target_workers
            self._last_scale_time = time.time()
            
            # 记录历史
            self._scale_history.append({
                "timestamp": time.time(),
                "operation": operation,
                "from": old_workers,
                "to": target_workers,
                "avg_load": sum(self._load_history) / len(self._load_history) if self._load_history else 0
            })
            
            logger.warning(
                f"自动扩缩容: {operation} "
                f"{old_workers} -> {target_workers} 工作线程"
            )
            
            return True
    
    def get_stats(self) -> Dict[str, Any]:
        """获取扩缩容统计信息"""
        with self._lock:
            return {
                "current_workers": self._current_workers,
                "min_workers": self.min_workers,
                "max_workers": self.max_workers,
                "last_scale_time": self._last_scale_time,
                "time_since_last_scale_sec": time.time() - self._last_scale_time,
                "scale_history": self._scale_history[-10:],  # 最近10次
                "total_scale_operations": len(self._scale_history),
                "avg_load": sum(self._load_history) / len(self._load_history) if self._load_history else 0
            }
    
    def reset(self) -> None:
        """重置扩缩容状态"""
        with self._lock:
            self._current_workers = self.min_workers
            self._last_scale_time = 0.0
            self._load_history.clear()
            logger.info("自动扩缩容状态已重置")


# 便捷函数
def create_resilience_manager(
    enable_graceful_degradation: bool = True,
    enable_exception_isolation: bool = True,
    enable_auto_scaling: bool = True
) -> Dict[str, Any]:
    """
    创建完整的弹性管理器集合
    
    Args:
        enable_graceful_degradation: 启用优雅降级
        enable_exception_isolation: 启用异常隔离
        enable_auto_scaling: 启用自动扩缩容
        
    Returns:
        Dict: 包含所有管理器的字典
    """
    managers = {}
    
    if enable_graceful_degradation:
        managers["degradation"] = GracefulDegradation()
    
    if enable_exception_isolation:
        managers["exception_isolation"] = ExceptionIsolation()
    
    if enable_auto_scaling:
        managers["auto_scaler"] = AutoScaler()
    
    return managers
