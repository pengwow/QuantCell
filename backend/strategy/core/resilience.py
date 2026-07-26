# -*- coding: utf-8 -*-
"""弹性机制模块 — 熔断器、优雅降级、自动扩缩容"""
from __future__ import annotations

import time
import threading
from enum import Enum
from typing import Any, Callable, Dict, Optional


class EventPriority(Enum):
    """事件优先级"""
    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3
    BACKGROUND = 4


class DegradationLevel(Enum):
    """降级级别"""
    NORMAL = 0
    LIGHT = 1
    MEDIUM = 2
    HEAVY = 3
    EMERGENCY = 4


class CircuitBreakerState(Enum):
    """熔断器状态"""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class DegradationConfig:
    """降级配置"""
    def __init__(self, max_priority: int):
        self.max_priority = max_priority


class GracefulDegradation:
    """优雅降级机制"""

    def __init__(self, on_level_change: Optional[Callable] = None):
        self.current_level = DegradationLevel.NORMAL
        self._level_change_count = 0
        self._on_level_change = on_level_change
        self._lock = threading.Lock()

        # 每个级别对应的最大优先级（只接受 <= max_priority 的事件）
        self._level_configs = {
            DegradationLevel.NORMAL: DegradationConfig(max_priority=4),
            DegradationLevel.LIGHT: DegradationConfig(max_priority=3),
            DegradationLevel.MEDIUM: DegradationConfig(max_priority=2),
            DegradationLevel.HEAVY: DegradationConfig(max_priority=1),
            DegradationLevel.EMERGENCY: DegradationConfig(max_priority=0),
        }

    @property
    def current_config(self) -> DegradationConfig:
        return self._level_configs[self.current_level]

    def should_accept_event(self, priority: EventPriority) -> bool:
        """判断是否接受事件"""
        with self._lock:
            return priority.value <= self.current_config.max_priority

    def update_level(self, load: float) -> DegradationLevel:
        """根据负载更新降级级别"""
        with self._lock:
            # 计算目标级别（与测试阈值对齐）
            if load < 0.7:
                target = DegradationLevel.NORMAL
            elif load <= 0.85:
                target = DegradationLevel.LIGHT
            elif load <= 0.95:
                target = DegradationLevel.MEDIUM
            elif load <= 0.99:
                target = DegradationLevel.HEAVY
            else:
                target = DegradationLevel.EMERGENCY

            # 恢复时每次只降级一级（逐步恢复）
            current_value = self.current_level.value
            target_value = target.value
            
            if target_value < current_value:
                # 降级（恢复）：每次只降一级
                target = DegradationLevel(current_value - 1)
                target_value = target.value

            # 避免频繁切换，只在级别变化时更新
            if target != self.current_level:
                old_level = self.current_level
                self.current_level = target
                self._level_change_count += 1

                if self._on_level_change:
                    self._on_level_change(old_level, target)

            return self.current_level

    def force_level(self, level: DegradationLevel) -> None:
        """强制设置降级级别"""
        with self._lock:
            self.current_level = level

    def reset(self) -> None:
        """重置状态"""
        with self._lock:
            self.current_level = DegradationLevel.NORMAL
            self._level_change_count = 0

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            return {
                "current_level": self.current_level.name,
                "level_change_count": self._level_change_count,
            }


class CircuitBreaker:
    """熔断器模式实现"""

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_max_calls: int = 2,
        success_threshold: int = 2
    ):
        self.name = name
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._half_open_max_calls = half_open_max_calls
        self._success_threshold = success_threshold

        self.state = CircuitBreakerState.CLOSED
        self._failures = 0
        self._successes = 0
        self._open_timestamp = 0.0
        self._half_open_calls = 0
        self._total_successes = 0
        self._total_failures = 0
        self._lock = threading.Lock()

    def can_execute(self) -> bool:
        """判断是否可以执行"""
        with self._lock:
            if self.state == CircuitBreakerState.CLOSED:
                return True

            if self.state == CircuitBreakerState.OPEN:
                # 检查是否超时
                if time.time() - self._open_timestamp >= self._recovery_timeout:
                    self.state = CircuitBreakerState.HALF_OPEN
                    self._half_open_calls = 1  # 第一次调用就占用配额
                    return True
                return False

            if self.state == CircuitBreakerState.HALF_OPEN:
                # 检查半开状态调用限制
                if self._half_open_calls < self._half_open_max_calls:
                    self._half_open_calls += 1
                    return True
                return False

            return False

    def record_success(self) -> None:
        """记录成功"""
        with self._lock:
            self._successes += 1
            self._total_successes += 1
            self._failures = 0

            if self.state == CircuitBreakerState.HALF_OPEN:
                if self._successes >= self._success_threshold:
                    self.state = CircuitBreakerState.CLOSED
                    self._successes = 0

    def record_failure(self) -> None:
        """记录失败"""
        with self._lock:
            self._failures += 1
            self._total_failures += 1
            self._successes = 0

            if self.state == CircuitBreakerState.CLOSED:
                if self._failures >= self._failure_threshold:
                    self.state = CircuitBreakerState.OPEN
                    self._open_timestamp = time.time()

            elif self.state == CircuitBreakerState.HALF_OPEN:
                # 半开状态下任何失败都立即打开
                self.state = CircuitBreakerState.OPEN
                self._open_timestamp = time.time()

    def reset(self) -> None:
        """重置熔断器"""
        with self._lock:
            self.state = CircuitBreakerState.CLOSED
            self._failures = 0
            self._successes = 0
            self._open_timestamp = 0.0
            self._half_open_calls = 0

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            return {
                "name": self.name,
                "state": self.state.value,
                "total_successes": self._total_successes,
                "total_failures": self._total_failures,
                "failures_since_last_reset": self._failures,
                "successes_since_last_reset": self._successes,
            }


class ExceptionIsolation:
    """异常隔离框架"""

    def __init__(self):
        self._handlers: Dict[str, Any] = {}
        self._dead_letter_queue: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

    def wrap_handler(
        self,
        event_type: str,
        handler: Callable,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0
    ) -> Callable:
        """包装处理器，添加异常隔离和熔断器"""
        breaker = CircuitBreaker(
            name=f"{event_type}_breaker",
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout
        )

        def wrapped(data: Any) -> bool:
            if not breaker.can_execute():
                # 熔断器打开，加入死信队列
                self._add_dead_letter(event_type, data)
                return False

            try:
                result = handler(data)
                breaker.record_success()
                return True
            except Exception:
                breaker.record_failure()
                self._add_dead_letter(event_type, data)
                return False

        wrapped._handler_id = event_type
        wrapped._breaker = breaker
        self._handlers[event_type] = {"handler": handler, "breaker": breaker}

        return wrapped

    def _add_dead_letter(self, event_type: str, data: Any) -> None:
        """添加到死信队列"""
        with self._lock:
            self._dead_letter_queue.append({
                "event_type": event_type,
                "data": data,
                "timestamp": time.time(),
            })

    def get_dead_letter_queue_size(self) -> int:
        """获取死信队列大小"""
        with self._lock:
            return len(self._dead_letter_queue)

    def get_dead_letter_items(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取死信队列项"""
        with self._lock:
            return self._dead_letter_queue[:limit]

    def get_handler_stats(self) -> Dict[str, Dict[str, Any]]:
        """获取所有处理器统计"""
        stats = {}
        with self._lock:
            for event_type, info in self._handlers.items():
                stats[event_type] = {
                    "total_calls": info["breaker"]._total_successes + info["breaker"]._total_failures,
                    "total_successes": info["breaker"]._total_successes,
                    "total_failures": info["breaker"]._total_failures,
                }
        return stats

    def reset_circuit_breaker(self, handler_id: str) -> bool:
        """重置指定处理器的熔断器"""
        with self._lock:
            if handler_id in self._handlers:
                self._handlers[handler_id]["breaker"].reset()
                return True
            return False

    def reset_all_circuit_breakers(self) -> None:
        """重置所有熔断器"""
        with self._lock:
            for info in self._handlers.values():
                info["breaker"].reset()


class AutoScaler:
    """自动扩缩容器"""

    def __init__(
        self,
        min_workers: int = 2,
        max_workers: int = 8,
        scale_up_threshold: float = 0.7,
        scale_down_threshold: float = 0.3,
        cooldown_period: float = 60.0
    ):
        self.min_workers = min_workers
        self.max_workers = max_workers
        self._scale_up_threshold = scale_up_threshold
        self._scale_down_threshold = scale_down_threshold
        self._cooldown_period = cooldown_period

        self._current_workers = min_workers
        self._load_history: list = []
        self._last_scale_time = 0.0
        self._scale_history: list = []
        self._lock = threading.Lock()

    @property
    def current_workers(self) -> int:
        return self._current_workers

    def record_load(self, load: float) -> None:
        """记录负载"""
        with self._lock:
            self._load_history.append(load)
            # 只保留最近100条记录
            if len(self._load_history) > 100:
                self._load_history = self._load_history[-100:]

    def evaluate_scaling(self) -> tuple[Optional[str], Optional[int]]:
        """评估是否需要扩缩容"""
        with self._lock:
            # 检查冷却期
            if time.time() - self._last_scale_time < self._cooldown_period:
                return None, None

            if not self._load_history:
                return None, None

            # 计算平均负载
            avg_load = sum(self._load_history) / len(self._load_history)

            if avg_load >= self._scale_up_threshold:
                target = min(self._current_workers * 2, self.max_workers)
                return "scale_up", target

            if avg_load <= self._scale_down_threshold:
                target = max(self._current_workers // 2, self.min_workers)
                return "scale_down", target

            return None, None

    def apply_scaling(self, operation: str, target: int) -> bool:
        """应用扩缩容"""
        with self._lock:
            # 限制在范围内
            target = max(self.min_workers, min(target, self.max_workers))

            if target == self._current_workers:
                return False

            self._last_scale_time = time.time()
            self._current_workers = target
            self._scale_history.append({
                "operation": operation,
                "target": target,
                "timestamp": time.time(),
            })

            return True

    def reset(self) -> None:
        """重置状态"""
        with self._lock:
            self._current_workers = self.min_workers
            self._load_history.clear()
            self._last_scale_time = 0.0
            self._scale_history.clear()

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            return {
                "current_workers": self._current_workers,
                "min_workers": self.min_workers,
                "max_workers": self.max_workers,
                "total_scale_operations": len(self._scale_history),
                "scale_history": self._scale_history,
            }


def create_resilience_manager(
    enable_graceful_degradation: bool = True,
    enable_circuit_breaker: bool = True,
    enable_exception_isolation: bool = True,
    enable_auto_scaling: bool = True
) -> Dict[str, Any]:
    """创建弹性管理器集合"""
    managers = {}

    if enable_graceful_degradation:
        managers["degradation"] = GracefulDegradation()

    if enable_exception_isolation:
        managers["exception_isolation"] = ExceptionIsolation()

    if enable_auto_scaling:
        managers["auto_scaler"] = AutoScaler()

    return managers


__all__ = [
    "GracefulDegradation",
    "CircuitBreaker",
    "CircuitBreakerState",
    "ExceptionIsolation",
    "AutoScaler",
    "EventPriority",
    "DegradationLevel",
    "create_resilience_manager",
]
