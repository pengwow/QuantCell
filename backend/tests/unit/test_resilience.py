"""
弹性机制单元测试 - 边界情况处理

测试范围:
- GracefulDegradation 优雅降级机制
- CircuitBreaker 熔断器模式
- ExceptionIsolation 异常隔离框架
- AutoScaler 自动扩缩容
"""

import pytest
import time
import threading
from unittest.mock import Mock, patch, MagicMock

from strategy.core.resilience import (
    GracefulDegradation,
    CircuitBreaker,
    CircuitBreakerState,
    ExceptionIsolation,
    AutoScaler,
    EventPriority,
    DegradationLevel,
    create_resilience_manager
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def graceful_degradation():
    """创建优雅降级实例"""
    return GracefulDegradation()


@pytest.fixture
def circuit_breaker():
    """创建熔断器实例"""
    return CircuitBreaker(
        name="test_breaker",
        failure_threshold=3,
        recovery_timeout=1.0,
        half_open_max_calls=2,
        success_threshold=2
    )


@pytest.fixture
def exception_isolation():
    """创建异常隔离实例"""
    return ExceptionIsolation()


@pytest.fixture
def auto_scaler():
    """创建自动扩缩容实例"""
    return AutoScaler(
        min_workers=2,
        max_workers=8,
        scale_up_threshold=0.7,
        scale_down_threshold=0.3,
        cooldown_period=0.5
    )


# =============================================================================
# GracefulDegradation 测试
# =============================================================================

class TestGracefulDegradation:
    """优雅降级机制测试类"""

    def test_initial_state(self, graceful_degradation):
        """测试初始状态"""
        assert graceful_degradation.current_level == DegradationLevel.NORMAL
        assert graceful_degradation.current_config.max_priority == 4

    def test_should_accept_event_normal(self, graceful_degradation):
        """测试正常模式下接受所有事件"""
        assert graceful_degradation.should_accept_event(EventPriority.CRITICAL) is True
        assert graceful_degradation.should_accept_event(EventPriority.HIGH) is True
        assert graceful_degradation.should_accept_event(EventPriority.NORMAL) is True
        assert graceful_degradation.should_accept_event(EventPriority.LOW) is True
        assert graceful_degradation.should_accept_event(EventPriority.BACKGROUND) is True

    def test_level_upgrade_light(self, graceful_degradation):
        """测试升级到轻度降级"""
        new_level = graceful_degradation.update_level(0.85)
        assert new_level == DegradationLevel.LIGHT
        assert graceful_degradation.current_level == DegradationLevel.LIGHT

    def test_level_upgrade_medium(self, graceful_degradation):
        """测试升级到中度降级"""
        graceful_degradation.update_level(0.85)  # 先升级到LIGHT
        new_level = graceful_degradation.update_level(0.95)
        assert new_level == DegradationLevel.MEDIUM

    def test_should_accept_event_light(self, graceful_degradation):
        """测试轻度下降级模式"""
        graceful_degradation.force_level(DegradationLevel.LIGHT)
        assert graceful_degradation.should_accept_event(EventPriority.CRITICAL) is True
        assert graceful_degradation.should_accept_event(EventPriority.BACKGROUND) is False

    def test_should_accept_event_emergency(self, graceful_degradation):
        """测试紧急模式"""
        graceful_degradation.force_level(DegradationLevel.EMERGENCY)
        assert graceful_degradation.should_accept_event(EventPriority.CRITICAL) is True
        assert graceful_degradation.should_accept_event(EventPriority.HIGH) is False
        assert graceful_degradation.should_accept_event(EventPriority.NORMAL) is False

    def test_auto_recovery(self, graceful_degradation):
        """测试自动恢复"""
        # 先升级到LIGHT
        graceful_degradation.update_level(0.85)
        assert graceful_degradation.current_level == DegradationLevel.LIGHT

        # 再升级到MEDIUM
        graceful_degradation.update_level(0.95)
        assert graceful_degradation.current_level == DegradationLevel.MEDIUM

        # 降低到恢复阈值以下
        new_level = graceful_degradation.update_level(0.60)
        assert new_level == DegradationLevel.LIGHT  # 应该降级一级

    def test_level_change_callback(self):
        """测试降级级别变化回调"""
        callback_called = False
        old_level_received = None
        new_level_received = None

        def on_change(old_level, new_level):
            nonlocal callback_called, old_level_received, new_level_received
            callback_called = True
            old_level_received = old_level
            new_level_received = new_level

        gd = GracefulDegradation(on_level_change=on_change)
        gd.update_level(0.85)

        assert callback_called is True
        assert old_level_received == DegradationLevel.NORMAL
        assert new_level_received == DegradationLevel.LIGHT

    def test_force_level(self, graceful_degradation):
        """测试强制设置降级级别"""
        graceful_degradation.force_level(DegradationLevel.HEAVY)
        assert graceful_degradation.current_level == DegradationLevel.HEAVY

    def test_get_stats(self, graceful_degradation):
        """测试获取统计信息"""
        graceful_degradation.update_level(0.85)
        graceful_degradation.should_accept_event(EventPriority.BACKGROUND)

        stats = graceful_degradation.get_stats()
        assert "current_level" in stats
        assert "level_change_count" in stats
        assert stats["level_change_count"] == 1

    def test_reset(self, graceful_degradation):
        """测试重置"""
        graceful_degradation.update_level(0.95)
        graceful_degradation.reset()

        assert graceful_degradation.current_level == DegradationLevel.NORMAL
        assert graceful_degradation.get_stats()["level_change_count"] == 0


# =============================================================================
# CircuitBreaker 测试
# =============================================================================

class TestCircuitBreaker:
    """熔断器测试类"""

    def test_initial_state(self, circuit_breaker):
        """测试初始状态"""
        assert circuit_breaker.state == CircuitBreakerState.CLOSED
        assert circuit_breaker.can_execute() is True

    def test_record_success(self, circuit_breaker):
        """测试记录成功"""
        circuit_breaker.record_success()
        assert circuit_breaker.get_stats()["total_successes"] == 1

    def test_open_after_failures(self, circuit_breaker):
        """测试连续失败后熔断器打开"""
        # 连续失败3次
        for _ in range(3):
            circuit_breaker.record_failure()

        assert circuit_breaker.state == CircuitBreakerState.OPEN
        assert circuit_breaker.can_execute() is False

    def test_half_open_after_timeout(self, circuit_breaker):
        """测试超时后进入半开状态"""
        # 先让熔断器打开
        for _ in range(3):
            circuit_breaker.record_failure()

        assert circuit_breaker.state == CircuitBreakerState.OPEN

        # 等待超时
        time.sleep(1.1)

        # 应该可以执行（进入半开状态）
        assert circuit_breaker.can_execute() is True
        assert circuit_breaker.state == CircuitBreakerState.HALF_OPEN

    def test_close_after_success_in_half_open(self, circuit_breaker):
        """测试半开状态成功后关闭"""
        # 先让熔断器打开
        for _ in range(3):
            circuit_breaker.record_failure()

        # 等待超时进入半开
        time.sleep(1.1)
        circuit_breaker.can_execute()

        # 记录2次成功
        circuit_breaker.record_success()
        circuit_breaker.record_success()

        assert circuit_breaker.state == CircuitBreakerState.CLOSED

    def test_reopen_after_failure_in_half_open(self, circuit_breaker):
        """测试半开状态失败后重新打开"""
        # 先让熔断器打开
        for _ in range(3):
            circuit_breaker.record_failure()

        # 等待超时进入半开
        time.sleep(1.1)
        circuit_breaker.can_execute()

        # 记录失败
        circuit_breaker.record_failure()

        assert circuit_breaker.state == CircuitBreakerState.OPEN

    def test_half_open_call_limit(self, circuit_breaker):
        """测试半开状态调用限制"""
        # 先让熔断器打开
        for _ in range(3):
            circuit_breaker.record_failure()

        # 等待超时进入半开
        time.sleep(1.1)

        # 前2次应该可以执行
        assert circuit_breaker.can_execute() is True
        assert circuit_breaker.can_execute() is True

        # 第3次应该被拒绝
        assert circuit_breaker.can_execute() is False

    def test_get_stats(self, circuit_breaker):
        """测试获取统计信息"""
        circuit_breaker.record_success()
        circuit_breaker.record_failure()

        stats = circuit_breaker.get_stats()
        assert stats["name"] == "test_breaker"
        assert stats["total_successes"] == 1
        assert stats["total_failures"] == 1

    def test_reset(self, circuit_breaker):
        """测试重置"""
        for _ in range(3):
            circuit_breaker.record_failure()

        assert circuit_breaker.state == CircuitBreakerState.OPEN

        circuit_breaker.reset()

        assert circuit_breaker.state == CircuitBreakerState.CLOSED
        assert circuit_breaker.can_execute() is True


# =============================================================================
# ExceptionIsolation 测试
# =============================================================================

class TestExceptionIsolation:
    """异常隔离框架测试类"""

    def test_wrap_handler_success(self, exception_isolation):
        """测试包装处理器成功执行"""
        def handler(data):
            return data * 2

        wrapped = exception_isolation.wrap_handler("TEST", handler)
        result = wrapped(5)

        assert result is True

    def test_wrap_handler_exception(self, exception_isolation):
        """测试包装处理器异常捕获"""
        def handler(data):
            raise ValueError("测试异常")

        wrapped = exception_isolation.wrap_handler("TEST", handler)
        result = wrapped(5)

        assert result is False

    def test_circuit_breaker_integration(self, exception_isolation):
        """测试熔断器集成"""
        call_count = 0

        def handler(data):
            nonlocal call_count
            call_count += 1
            raise ValueError("测试异常")

        wrapped = exception_isolation.wrap_handler(
            "TEST", handler, failure_threshold=2, recovery_timeout=0.5
        )

        # 连续失败2次
        wrapped(1)
        wrapped(2)

        # 第3次应该被熔断器阻止
        result = wrapped(3)
        assert result is False
        assert call_count == 2  # 只执行了2次

    def test_dead_letter_queue(self, exception_isolation):
        """测试死信队列"""
        def handler(data):
            raise ValueError("测试异常")

        wrapped = exception_isolation.wrap_handler("TEST", handler)
        wrapped("test_data")

        # 检查死信队列
        assert exception_isolation.get_dead_letter_queue_size() == 1

        items = exception_isolation.get_dead_letter_items(1)
        assert len(items) == 1
        assert items[0]["event_type"] == "TEST"
        assert items[0]["data"] == "test_data"

    def test_handler_stats(self, exception_isolation):
        """测试处理器统计"""
        def handler(data):
            if data == "fail":
                raise ValueError("测试异常")
            return True

        wrapped = exception_isolation.wrap_handler("TEST", handler)

        wrapped("success")
        wrapped("fail")
        wrapped("success")

        stats = exception_isolation.get_handler_stats()
        assert len(stats) == 1

        handler_stats = list(stats.values())[0]
        assert handler_stats["total_calls"] == 3
        assert handler_stats["total_successes"] == 2
        assert handler_stats["total_failures"] == 1

    def test_reset_circuit_breaker(self, exception_isolation):
        """测试重置熔断器"""
        def handler(data):
            raise ValueError("测试异常")

        wrapped = exception_isolation.wrap_handler(
            "TEST", handler, failure_threshold=1
        )

        wrapped(1)

        # 获取handler_id
        handler_id = wrapped._handler_id

        # 重置熔断器
        result = exception_isolation.reset_circuit_breaker(handler_id)
        assert result is True

    def test_reset_all_circuit_breakers(self, exception_isolation):
        """测试重置所有熔断器"""
        def handler1(data):
            raise ValueError("测试异常")

        def handler2(data):
            raise ValueError("测试异常")

        wrapped1 = exception_isolation.wrap_handler("TEST1", handler1, failure_threshold=1)
        wrapped2 = exception_isolation.wrap_handler("TEST2", handler2, failure_threshold=1)

        wrapped1(1)
        wrapped2(1)

        exception_isolation.reset_all_circuit_breakers()

        # 应该可以再次执行
        assert wrapped1(2) is False  # 仍然会失败，但熔断器已重置


# =============================================================================
# AutoScaler 测试
# =============================================================================

class TestAutoScaler:
    """自动扩缩容测试类"""

    def test_initial_state(self, auto_scaler):
        """测试初始状态"""
        assert auto_scaler.current_workers == 2
        assert auto_scaler.min_workers == 2
        assert auto_scaler.max_workers == 8

    def test_record_load(self, auto_scaler):
        """测试记录负载"""
        auto_scaler.record_load(0.5)
        auto_scaler.record_load(0.6)

        assert len(auto_scaler._load_history) == 2

    def test_evaluate_scale_up(self, auto_scaler):
        """测试评估扩容"""
        # 记录高负载
        for _ in range(10):
            auto_scaler.record_load(0.8)

        # 等待冷却期
        time.sleep(0.6)

        operation, target = auto_scaler.evaluate_scaling()

        assert operation == "scale_up"
        assert target > 2

    def test_evaluate_scale_down(self, auto_scaler):
        """测试评估缩容"""
        # 先扩容
        auto_scaler._current_workers = 6

        # 记录低负载
        for _ in range(10):
            auto_scaler.record_load(0.2)

        # 等待冷却期
        time.sleep(0.6)

        operation, target = auto_scaler.evaluate_scaling()

        assert operation == "scale_down"
        assert target < 6

    def test_cooldown_period(self, auto_scaler):
        """测试冷却期"""
        # 先执行一次扩容
        auto_scaler.apply_scaling("scale_up", 4)

        # 立即评估，应该返回None（在冷却期内）
        auto_scaler.record_load(0.9)
        operation, target = auto_scaler.evaluate_scaling()

        assert operation is None

    def test_apply_scaling(self, auto_scaler):
        """测试应用扩缩容"""
        result = auto_scaler.apply_scaling("scale_up", 4)

        assert result is True
        assert auto_scaler.current_workers == 4

    def test_max_workers_limit(self, auto_scaler):
        """测试最大工作线程限制"""
        result = auto_scaler.apply_scaling("scale_up", 100)

        assert auto_scaler.current_workers == 8  # 被限制在max_workers

    def test_min_workers_limit(self, auto_scaler):
        """测试最小工作线程限制"""
        auto_scaler._current_workers = 4
        result = auto_scaler.apply_scaling("scale_down", 1)

        assert auto_scaler.current_workers == 2  # 被限制在min_workers

    def test_get_stats(self, auto_scaler):
        """测试获取统计信息"""
        auto_scaler.apply_scaling("scale_up", 4)

        stats = auto_scaler.get_stats()
        assert stats["current_workers"] == 4
        assert stats["total_scale_operations"] == 1
        assert len(stats["scale_history"]) == 1

    def test_reset(self, auto_scaler):
        """测试重置"""
        auto_scaler.apply_scaling("scale_up", 6)
        auto_scaler.reset()

        assert auto_scaler.current_workers == 2
        assert len(auto_scaler._load_history) == 0


# =============================================================================
# 集成测试
# =============================================================================

class TestResilienceIntegration:
    """弹性机制集成测试类"""

    def test_create_resilience_manager(self):
        """测试创建弹性管理器集合"""
        managers = create_resilience_manager()

        assert "degradation" in managers
        assert "exception_isolation" in managers
        assert "auto_scaler" in managers

    def test_create_resilience_manager_partial(self):
        """测试创建部分弹性管理器"""
        managers = create_resilience_manager(
            enable_graceful_degradation=True,
            enable_exception_isolation=False,
            enable_auto_scaling=False
        )

        assert "degradation" in managers
        assert "exception_isolation" not in managers
        assert "auto_scaler" not in managers

    def test_degradation_with_events(self):
        """测试降级机制与事件处理集成"""
        gd = GracefulDegradation()

        # 模拟队列使用率上升
        gd.update_level(0.85)
        assert gd.current_level == DegradationLevel.LIGHT

        # BACKGROUND事件应该被拒绝
        assert gd.should_accept_event(EventPriority.BACKGROUND) is False

        # CRITICAL事件应该被接受
        assert gd.should_accept_event(EventPriority.CRITICAL) is True

    def test_circuit_breaker_state_transitions(self):
        """测试熔断器状态转换"""
        cb = CircuitBreaker(
            name="test",
            failure_threshold=2,
            recovery_timeout=0.1,
            success_threshold=1
        )

        # CLOSED -> OPEN
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN

        # OPEN -> HALF_OPEN
        time.sleep(0.15)
        assert cb.can_execute() is True
        assert cb.state == CircuitBreakerState.HALF_OPEN

        # HALF_OPEN -> CLOSED
        cb.record_success()
        assert cb.state == CircuitBreakerState.CLOSED

    def test_exception_isolation_with_circuit_breaker(self):
        """测试异常隔离与熔断器集成"""
        ei = ExceptionIsolation()

        failure_count = 0

        def failing_handler(data):
            nonlocal failure_count
            failure_count += 1
            raise ValueError("测试异常")

        wrapped = ei.wrap_handler(
            "TEST", failing_handler, failure_threshold=2, recovery_timeout=0.5
        )

        # 前2次会实际执行
        wrapped(1)
        wrapped(2)

        # 第3次应该被熔断器阻止
        wrapped(3)

        assert failure_count == 2

    @pytest.mark.slow
    def test_auto_scaler_with_load(self):
        """测试自动扩缩容与负载集成"""
        scaler = AutoScaler(
            min_workers=2,
            max_workers=8,
            cooldown_period=0.1
        )

        # 模拟高负载
        for _ in range(10):
            scaler.record_load(0.9)

        # 等待冷却期
        time.sleep(0.15)

        operation, target = scaler.evaluate_scaling()

        assert operation == "scale_up"
        assert target > 2


# =============================================================================
# 性能基准测试
# =============================================================================

class TestResiliencePerformanceBenchmarks:
    """弹性机制性能基准测试类"""

    @pytest.mark.slow
    def test_graceful_degradation_performance(self):
        """测试优雅降级性能"""
        gd = GracefulDegradation()

        iterations = 100000
        start = time.time()

        for i in range(iterations):
            gd.should_accept_event(EventPriority.NORMAL)

        elapsed = time.time() - start
        ops_per_sec = iterations / elapsed

        print(f"\n优雅降级检查性能: {ops_per_sec:.0f} 操作/秒")
        assert ops_per_sec > 1000000  # 应该达到百万级

    @pytest.mark.slow
    def test_circuit_breaker_performance(self):
        """测试熔断器性能"""
        cb = CircuitBreaker(name="perf_test")

        iterations = 100000
        start = time.time()

        for _ in range(iterations):
            cb.can_execute()
            cb.record_success()

        elapsed = time.time() - start
        ops_per_sec = iterations / elapsed

        print(f"\n熔断器操作性能: {ops_per_sec:.0f} 操作/秒")
        assert ops_per_sec > 500000

    @pytest.mark.slow
    def test_exception_isolation_performance(self):
        """测试异常隔离性能"""
        ei = ExceptionIsolation()

        def handler(data):
            return data * 2

        wrapped = ei.wrap_handler("PERF", handler)

        iterations = 10000
        start = time.time()

        for i in range(iterations):
            wrapped(i)

        elapsed = time.time() - start
        ops_per_sec = iterations / elapsed

        print(f"\n异常隔离包装处理器性能: {ops_per_sec:.0f} 操作/秒")
        assert ops_per_sec > 10000
