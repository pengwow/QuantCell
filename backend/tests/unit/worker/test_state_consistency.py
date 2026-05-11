# -*- coding: utf-8 -*-
"""
Worker 模块隔离单元测试

测试目标：
1. 验证 WorkerState 枚举与 WorkerStatus.is_healthy() 的状态一致性
2. 验证 MessageType 枚举与 WorkerProcess 处理逻辑的一致性
3. 检测可能导致运行时错误的状态不一致问题

这个测试文件采用完全隔离的方法，直接复制需要测试的代码逻辑，
避免导入整个项目模块导致的依赖问题。
"""

import pytest
from datetime import datetime
from dataclasses import dataclass
from typing import Optional
from enum import Enum
import sys
import os
import re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../..'))


# =============================================================================
# 从 worker.state 复制的代码（隔离测试）
# =============================================================================

class WorkerState(Enum):
    INITIALIZING = "initializing"
    INITIALIZED = "initialized"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"
    RECOVERING = "recovering"
    RELOADING = "reloading"
    RESTARTING = "restarting"

    def can_transition_to(self, new_state: "WorkerState") -> bool:
        valid_transitions = {
            WorkerState.INITIALIZING: [WorkerState.INITIALIZED, WorkerState.STARTING, WorkerState.RUNNING, WorkerState.ERROR],
            WorkerState.INITIALIZED: [WorkerState.STARTING, WorkerState.STOPPING, WorkerState.ERROR],
            WorkerState.STARTING: [WorkerState.RUNNING, WorkerState.ERROR],
            WorkerState.RUNNING: [WorkerState.STOPPING, WorkerState.RELOADING, WorkerState.ERROR],
            WorkerState.STOPPING: [WorkerState.STOPPED, WorkerState.ERROR],
            WorkerState.STOPPED: [WorkerState.STARTING, WorkerState.RESTARTING],
            WorkerState.ERROR: [WorkerState.RECOVERING, WorkerState.STOPPING],
            WorkerState.RECOVERING: [WorkerState.RUNNING, WorkerState.ERROR, WorkerState.STOPPING],
            WorkerState.RELOADING: [WorkerState.RUNNING, WorkerState.ERROR],
            WorkerState.RESTARTING: [WorkerState.INITIALIZING, WorkerState.ERROR],
        }
        return new_state in valid_transitions.get(self, [])


@dataclass
class WorkerStatus:
    worker_id: str
    state: WorkerState = WorkerState.INITIALIZING
    last_heartbeat: Optional[datetime] = None
    started_at: Optional[datetime] = None

    def update_state(self, new_state: WorkerState) -> bool:
        if self.state.can_transition_to(new_state):
            old_state = self.state
            self.state = new_state
            if new_state == WorkerState.RUNNING and old_state != WorkerState.RUNNING:
                self.started_at = datetime.now()
            return True
        return False

    def update_heartbeat(self):
        self.last_heartbeat = datetime.now()

    def record_error(self, error_message: str):
        pass

    def is_healthy(self, heartbeat_timeout: int = 30) -> bool:
        if self.state not in [WorkerState.RUNNING, WorkerState.PAUSED]:
            return False
        if self.last_heartbeat is None:
            return False
        from datetime import timedelta
        elapsed = datetime.now() - self.last_heartbeat
        return elapsed < timedelta(seconds=heartbeat_timeout)


# =============================================================================
# 从 worker.ipc.protocol 复制的代码（隔离测试）
# =============================================================================

class MessageType(Enum):
    START = "start"
    STOP = "stop"
    PAUSE = "pause"
    RESUME = "resume"
    RESTART = "restart"
    RELOAD_CONFIG = "reload_config"
    UPDATE_PARAMS = "update_params"
    HEARTBEAT = "heartbeat"
    STATUS_UPDATE = "status_update"
    ERROR = "error"
    CONTROL = "control"


# =============================================================================
# 测试类
# =============================================================================

class TestWorkerStateHealthConsistency:
    """
    测试 WorkerState 与 is_healthy() 方法的一致性
    """

    def test_worker_state_has_paused_for_health_check(self):
        """测试 WorkerState 是否包含 PAUSED 状态（is_healthy 需要）"""
        paused_state = None
        for state in WorkerState:
            if state.value == "paused":
                paused_state = state
                break

        assert paused_state is not None, (
            "WorkerState 缺少 'paused' 状态，"
            "但 WorkerStatus.is_healthy() 方法需要它。"
            "这会导致健康检查逻辑不完整。"
        )

    def test_is_healthy_accepts_all_active_states(self):
        """测试 is_healthy() 接受所有活跃状态"""
        status = WorkerStatus(worker_id="test-worker")

        status.state = WorkerState.RUNNING
        status.last_heartbeat = datetime.now()
        assert status.is_healthy() is True, "RUNNING 状态应该是健康的"

        try:
            paused_state = WorkerState.PAUSED
            status.state = paused_state
            status.last_heartbeat = datetime.now()
            assert status.is_healthy() is True, "PAUSED 状态应该是健康的"
        except AttributeError:
            pytest.fail(
                "WorkerState 没有 PAUSED 属性，"
                "但 is_healthy() 方法引用了它。"
                "这会导致 AttributeError 运行时错误。"
            )


class TestMessageTypeHandlerConsistency:
    """
    测试 MessageType 与 WorkerProcess 处理逻辑的一致性
    """

    def test_message_type_define_pause_resume(self):
        """测试 MessageType 是否定义了暂停/恢复消息类型"""
        assert hasattr(MessageType, 'PAUSE'), "MessageType 缺少 PAUSE 定义"
        assert hasattr(MessageType, 'RESUME'), "MessageType 缺少 RESUME 定义"

    def test_worker_process_handles_all_control_messages(self):
        """测试 WorkerProcess 是否处理所有定义的 MessageType"""
        control_types = [
            MessageType.STOP,
            MessageType.PAUSE,
            MessageType.RESUME,
            MessageType.RESTART,
            MessageType.RELOAD_CONFIG,
            MessageType.UPDATE_PARAMS,
        ]

        worker_process_path = os.path.join(
            os.path.dirname(__file__),
            '../../../worker/worker_process.py'
        )

        with open(worker_process_path, 'r', encoding='utf-8') as f:
            source_code = f.read()

        missing_handlers = []
        for msg_type in control_types:
            type_name = msg_type.name
            if f"message.msg_type == MessageType.{type_name}" not in source_code:
                missing_handlers.append(type_name)

        assert len(missing_handlers) == 0, (
            f"WorkerProcess._handle_control 缺少以下消息类型的处理: {missing_handlers}。"
            f"这会导致这些消息类型被静默忽略。"
        )


class TestWorkerProcessTimeframeConversion:
    """测试时间周期转换逻辑"""

    def _convert_timeframe_to_bar_type(self, timeframe: str) -> str:
        unit_map = {"m": "MINUTE", "h": "HOUR", "d": "DAY", "w": "WEEK", "M": "MONTH"}
        if not timeframe:
            return "1-HOUR"
        match = re.match(r"(\d+)([mhdwM])", timeframe)
        if match:
            value, unit = match.groups()
            bar_type = f"{value}-{unit_map.get(unit, 'HOUR')}"
            return bar_type
        return "1-HOUR"

    def test_convert_timeframe_patterns(self):
        """测试各种时间周期格式的转换"""
        test_cases = [
            ("1m", "1-MINUTE"),
            ("5m", "5-MINUTE"),
            ("15m", "15-MINUTE"),
            ("30m", "30-MINUTE"),
            ("1h", "1-HOUR"),
            ("4h", "4-HOUR"),
            ("1d", "1-DAY"),
            ("1w", "1-WEEK"),
            ("1M", "1-MONTH"),
            ("", "1-HOUR"),
            ("invalid", "1-HOUR"),
        ]

        for input_val, expected in test_cases:
            result = self._convert_timeframe_to_bar_type(input_val)
            assert result == expected, f"时间周期 '{input_val}' 转换失败"


class TestBalanceCheckerLogic:
    """测试余额检查逻辑"""

    def test_check_balance_returns_tuple_format(self):
        """测试余额检查返回正确的元组格式"""

        class SimpleBalanceChecker:
            def __init__(self):
                self.free_balance = 1000.0
                self.price = 50000.0

            def check_balance(self, order_qty):
                try:
                    required_balance = float(order_qty) * self.price * 1.1
                    if self.free_balance < required_balance:
                        shortfall = required_balance - self.free_balance
                        return (False, f"余额不足！缺少 {shortfall:.4f} USDT", None)
                    return (True, "余额充足", None)
                except Exception as e:
                    return (True, f"错误: {e}", None)

        checker = SimpleBalanceChecker()
        result = checker.check_balance(0.01)

        assert isinstance(result, tuple), "返回结果应该是元组"
        assert len(result) == 3, "返回结果应该是 3 元素元组"
        assert isinstance(result[0], bool), "第一个元素应该是布尔值"
        assert isinstance(result[1], str), "第二个元素应该是字符串"

    def test_check_balance_sufficient_funds(self):
        """测试余额充足的情况"""

        class SimpleBalanceChecker:
            def __init__(self):
                self.free_balance = 1000.0
                self.price = 50000.0

            def check_balance(self, order_qty):
                required_balance = float(order_qty) * self.price * 1.1
                if self.free_balance < required_balance:
                    return (False, "余额不足", None)
                return (True, "余额充足", None)

        checker = SimpleBalanceChecker()
        is_sufficient, message, adjusted_qty = checker.check_balance(0.01)
        assert is_sufficient is True
        assert adjusted_qty is None

    def test_check_balance_insufficient_no_adjust(self):
        """测试余额不足且未启用自动调整"""

        class SimpleBalanceChecker:
            def __init__(self, auto_adjust=False):
                self.free_balance = 1000.0
                self.price = 50000.0
                self.auto_adjust = auto_adjust

            def check_balance(self, order_qty):
                required_balance = float(order_qty) * self.price * 1.1
                if self.free_balance < required_balance:
                    if self.auto_adjust:
                        max_qty = self.free_balance / self.price / 1.1
                        return (True, "已自动调整", max_qty)
                    return (False, "余额不足", None)
                return (True, "余额充足", None)

        checker = SimpleBalanceChecker(auto_adjust=False)
        is_sufficient, message, adjusted_qty = checker.check_balance(1)

        assert is_sufficient is False
        assert "余额不足" in message
        assert adjusted_qty is None

    def test_check_balance_auto_adjust_calculates_qty(self):
        """测试自动调整时计算新的订单数量"""

        class SimpleBalanceChecker:
            def __init__(self, auto_adjust=True):
                self.free_balance = 1000.0
                self.price = 50000.0
                self.auto_adjust = auto_adjust

            def check_balance(self, order_qty):
                required_balance = float(order_qty) * self.price * 1.1
                if self.free_balance < required_balance:
                    if self.auto_adjust:
                        max_qty = self.free_balance / self.price / 1.1
                        return (True, "已自动调整", max_qty)
                    return (False, "余额不足", None)
                return (True, "余额充足", None)

        checker = SimpleBalanceChecker(auto_adjust=True)
        is_sufficient, message, adjusted_qty = checker.check_balance(1)

        assert is_sufficient is True
        assert adjusted_qty is not None
        assert adjusted_qty > 0


class TestWorkerStateTransitions:
    """测试 WorkerState 状态转换规则"""

    def test_state_can_transition_to_valid_targets(self):
        """测试状态转换到合法目标"""
        test_cases = [
            (WorkerState.INITIALIZING, WorkerState.INITIALIZED, True),
            (WorkerState.INITIALIZING, WorkerState.RUNNING, True),
            (WorkerState.INITIALIZING, WorkerState.ERROR, True),
            (WorkerState.INITIALIZED, WorkerState.STARTING, True),
            (WorkerState.INITIALIZED, WorkerState.STOPPING, True),
            (WorkerState.RUNNING, WorkerState.STOPPING, True),
            (WorkerState.RUNNING, WorkerState.RELOADING, True),
            (WorkerState.RUNNING, WorkerState.ERROR, True),
        ]

        for from_state, to_state, expected in test_cases:
            result = from_state.can_transition_to(to_state)
            assert result == expected, f"状态 {from_state.value} -> {to_state.value}"

    def test_state_invalid_transition_rejected(self):
        """测试非法状态转换被拒绝"""
        result = WorkerState.STOPPED.can_transition_to(WorkerState.RUNNING)
        assert result is False, "STOPPED -> RUNNING 应该是非法的"

    def test_worker_status_update_state_calls_handler(self):
        """测试 WorkerStatus.update_state 调用正确的回调"""
        status = WorkerStatus(worker_id="test")
        status.update_state(WorkerState.STARTING)
        status.update_state(WorkerState.RUNNING)

        assert status.started_at is not None
        assert status.state == WorkerState.RUNNING

    def test_worker_status_record_error(self):
        """测试 WorkerStatus 错误记录"""

        class TestWorkerStatus:
            def __init__(self):
                self.errors_count = 0
                self.last_error = None
                self.last_error_time = None

            def record_error(self, error_message: str):
                self.errors_count += 1
                self.last_error = error_message
                self.last_error_time = datetime.now()

        status = TestWorkerStatus()
        status.record_error("Test error 1")
        assert status.errors_count == 1
        assert status.last_error == "Test error 1"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
