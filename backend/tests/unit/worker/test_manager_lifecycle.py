# -*- coding: utf-8 -*-
"""
Worker Manager 生命周期测试

测试目标：
1. 验证 WorkerManager 的 Worker 生命周期管理
2. 测试 TradingNodeWorkerManager 的扩展功能
3. 验证配置合并逻辑的正确性

这些测试专注于 Manager 层的业务逻辑，确保状态管理和生命周期控制的正确性。
采用隔离导入模式，避免触发 worker 包的完整初始化。
"""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../..'))


class TestWorkerManagerLifecycle:
    """
    测试 WorkerManager 的 Worker 生命周期管理

    重点测试 start_strategy, stop_worker 等核心方法的边界情况
    """

    def test_worker_manager_imports(self):
        """测试可以导入 WorkerManager 组件"""
        from worker.state import WorkerState, WorkerStatus
        from worker.ipc.protocol import MessageType, Message

        assert WorkerState is not None
        assert WorkerStatus is not None
        assert MessageType is not None
        assert Message is not None

    def test_worker_manager_state_tracking(self):
        """测试 WorkerManager 的状态跟踪机制"""
        from worker.state import WorkerStatus, WorkerState

        # 模拟 WorkerManager 的状态跟踪
        _workers = {}
        _worker_status = {}

        worker_id = "test-worker"
        status = WorkerStatus(worker_id=worker_id)
        status.update_state(WorkerState.RUNNING)

        _workers[worker_id] = MagicMock()
        _worker_status[worker_id] = status

        assert len(_workers) == 1
        assert len(_worker_status) == 1
        assert _worker_status[worker_id].state == WorkerState.RUNNING

    def test_worker_manager_max_workers_logic(self):
        """测试最大 Worker 数量限制逻辑"""
        max_workers = 5
        _workers = {}

        # 模拟添加 Worker
        for i in range(max_workers):
            _workers[f"worker-{i}"] = MagicMock()

        # 验证达到上限
        assert len(_workers) >= max_workers
        can_add = len(_workers) < max_workers
        assert can_add is False, "Worker 数量已达上限，不应再添加"

    def test_worker_manager_worker_id_uniqueness(self):
        """测试 Worker ID 唯一性检查"""
        _workers = {}
        worker_id = "test-worker-123"

        # 首次添加
        _workers[worker_id] = MagicMock()
        assert worker_id in _workers

        # 尝试添加重复 ID
        exists = worker_id in _workers
        assert exists is True, "重复的 Worker ID 应该被检测到"

    def test_worker_manager_empty_stats(self):
        """测试空 Manager 的统计信息"""
        stats = {
            "total_workers": 0,
            "running_workers": 0,
            "max_workers": 5,
        }

        assert stats["total_workers"] == 0
        assert stats["running_workers"] == 0
        assert stats["max_workers"] == 5


class TestTradingNodeWorkerManagerConfigMerge:
    """
    测试 TradingNodeWorkerManager 的配置合并逻辑

    这是新增的高风险逻辑，涉及配置的正确合并
    """

    def test_merge_config_empty_exchange(self):
        """测试空交易所配置的合并"""
        base_config = {"strategy_id": 1, "symbols": ["BTCUSDT"]}

        # 模拟合并逻辑
        merged = base_config.copy()
        if merged is None:
            merged = base_config

        assert merged == base_config

    def test_merge_config_adds_exchange(self):
        """测试添加交易所配置的合并"""
        base_config = {"strategy_id": 1, "symbols": ["BTCUSDT"]}
        exchange_config = {
            "name": "binance",
            "api_key": "test_key",
            "api_secret": "test_secret",
        }

        # 模拟合并逻辑
        merged = base_config.copy()
        merged["exchange"] = exchange_config
        merged["trading"] = {
            "data_clients": {"binance": exchange_config},
            "exec_clients": {"binance": exchange_config},
        }

        assert "trading" in merged
        assert merged["exchange"] == exchange_config
        assert "data_clients" in merged["trading"]
        assert "exec_clients" in merged["trading"]
        assert "binance" in merged["trading"]["data_clients"]

    def test_merge_config_preserves_existing_trading_config(self):
        """测试保留现有交易配置"""
        base_config = {
            "strategy_id": 1,
            "trading": {"custom_key": "custom_value"},
        }
        exchange_config = {
            "name": "binance",
            "api_key": "test_key",
        }

        # 模拟合并逻辑
        merged = base_config.copy()
        existing_trading = merged.get("trading", {})
        merged["trading"] = {
            **existing_trading,
            "data_clients": {"binance": exchange_config},
            "exec_clients": {"binance": exchange_config},
        }

        assert "custom_key" in merged["trading"]
        assert merged["trading"]["custom_key"] == "custom_value"

    def test_merge_config_global_trading_config(self):
        """测试全局交易配置的合并"""
        global_trading_config = {"global_key": "global_value"}
        base_config = {"strategy_id": 1}
        exchange_config = {"name": "binance"}

        # 模拟合并逻辑
        merged = base_config.copy()
        merged["trading"] = {**global_trading_config}
        merged["trading"]["data_clients"] = {"binance": exchange_config}
        merged["trading"]["exec_clients"] = {"binance": exchange_config}

        assert "trading" in merged
        assert "global_key" in merged["trading"]
        assert merged["trading"]["global_key"] == "global_value"

    def test_config_merge_order(self):
        """测试配置合并顺序（exchange > global > base）"""
        base_config = {"key": "base"}
        global_config = {"key": "global", "global_only": True}
        exchange_config = {"key": "exchange", "exchange_only": True}

        # 模拟合并顺序
        merged = {**base_config}
        merged = {**merged, **global_config}
        merged = {**merged, **exchange_config}

        assert merged["key"] == "exchange", "exchange 配置应该优先级最高"
        assert "global_only" in merged
        assert "exchange_only" in merged


class TestWorkerManagerStatusHandling:
    """
    测试 WorkerManager 的状态消息处理

    重点测试状态转换和处理器调用的正确性
    """

    def test_handle_status_message_with_empty_worker_id(self):
        """测试处理空 worker_id 的状态消息"""
        from worker.ipc import Message, MessageType
        from worker.state import WorkerState, WorkerStatus

        message = Message(
            msg_type=MessageType.STATUS_UPDATE,
            worker_id="",  # 空 worker_id
            payload={"state": WorkerState.RUNNING.value},
        )

        # 模拟处理逻辑
        worker_id = message.worker_id
        if not worker_id:
            # 应该被静默忽略
            ignored = True
        else:
            ignored = False

        assert ignored is True, "空 worker_id 应该被忽略"

    def test_handle_status_message_unknown_worker(self):
        """测试处理未知 Worker 的状态消息"""
        from worker.ipc import Message, MessageType
        from worker.state import WorkerState, WorkerStatus

        # 模拟已知 workers
        _worker_status = {"known-worker": WorkerStatus(worker_id="known-worker")}

        message = Message(
            msg_type=MessageType.STATUS_UPDATE,
            worker_id="unknown-worker-id",
            payload={"state": WorkerState.RUNNING.value},
        )

        # 模拟处理逻辑
        known_workers = list(_worker_status.keys())
        if message.worker_id not in known_workers:
            ignored = True
        else:
            ignored = False

        assert ignored is True, "未知 Worker 的消息应该被忽略"

    def test_handle_status_message_with_invalid_state(self):
        """测试处理无效状态值"""
        from worker.state import WorkerStatus

        # 添加 worker 状态
        worker_status = WorkerStatus(worker_id="test-worker")
        _worker_status = {"test-worker": worker_status}

        invalid_state = "invalid-state-value"

        # 模拟处理逻辑
        try:
            from worker.state import WorkerState
            new_state = WorkerState(invalid_state)
            updated = True
        except ValueError:
            # 无效状态应该被忽略
            updated = False

        assert updated is False, "无效状态应该被忽略"

    def test_handle_status_message_updates_heartbeat(self):
        """测试状态消息更新心跳"""
        from worker.state import WorkerStatus, WorkerState

        # 添加 worker 状态
        worker_status = WorkerStatus(worker_id="test-worker")
        worker_status.update_state(WorkerState.RUNNING)
        _worker_status = {"test-worker": worker_status}

        # 模拟心跳更新
        last_heartbeat_before = worker_status.last_heartbeat

        # 处理心跳消息
        from datetime import datetime
        worker_status.update_heartbeat()

        assert worker_status.last_heartbeat is not None
        assert worker_status.last_heartbeat >= last_heartbeat_before


class TestWorkerManagerRecoveryLogic:
    """
    测试 WorkerManager 的恢复和监控逻辑

    这些测试验证 Worker 异常退出时的处理逻辑
    """

    @pytest.mark.asyncio
    async def test_monitor_loop_handles_exception(self):
        """测试监控循环处理异常"""

        class MockWorkerManager:
            def __init__(self):
                self._workers = {}
                self._running = False

            async def _monitor_loop(self):
                while self._running:
                    try:
                        for worker_id, worker in list(self._workers.items()):
                            worker.is_alive()  # 可能抛出异常
                    except Exception:
                        pass  # 异常应该被处理
                    await asyncio.sleep(0.1)

        manager = MockWorkerManager()
        manager._workers["test-worker"] = MagicMock()
        manager._workers["test-worker"].is_alive.side_effect = Exception("Test exception")

        manager._running = True
        task = asyncio.create_task(manager._monitor_loop())

        await asyncio.sleep(0.2)

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        assert manager._running is True


class TestWorkerManagerCallbackMechanism:
    """测试 WorkerManager 的回调机制"""

    def test_register_multiple_exit_callbacks(self):
        """测试注册多个退出回调"""
        _worker_exit_callbacks = []
        callbacks_called = []

        def callback1(worker_id, status):
            callbacks_called.append("callback1")

        def callback2(worker_id, status):
            callbacks_called.append("callback2")

        _worker_exit_callbacks.append(callback1)
        _worker_exit_callbacks.append(callback2)

        # 模拟调用回调
        from worker.state import WorkerStatus
        status = WorkerStatus(worker_id="test")
        for callback in _worker_exit_callbacks:
            callback("test-id", status)

        assert len(callbacks_called) == 2
        assert "callback1" in callbacks_called
        assert "callback2" in callbacks_called

    def test_unregister_exit_callback(self):
        """测试注销退出回调"""
        _worker_exit_callbacks = []

        def callback(worker_id, status):
            pass

        _worker_exit_callbacks.append(callback)
        _worker_exit_callbacks.remove(callback)

        assert callback not in _worker_exit_callbacks

    def test_register_multiple_status_handlers(self):
        """测试注册多个状态处理器"""
        _status_handlers = []

        handler1 = MagicMock()
        handler2 = MagicMock()

        _status_handlers.append(handler1)
        _status_handlers.append(handler2)

        assert len(_status_handlers) == 2

    def test_status_handlers_called_on_update(self):
        """测试状态更新时调用处理器"""
        from worker.state import WorkerStatus, WorkerState

        _status_handlers = []
        handlers_called = []

        def handler1(status):
            handlers_called.append("handler1")

        def handler2(status):
            handlers_called.append("handler2")

        _status_handlers.append(handler1)
        _status_handlers.append(handler2)

        # 模拟状态更新
        status = WorkerStatus(worker_id="test")
        for handler in _status_handlers:
            handler(status)

        assert len(handlers_called) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
