"""WorkerCoreService 启停与 WorkerOrchestrator status 查询测试。

Task 5 后 start/stop 走进程内直调（worker_system），orchestrator 仅保留
status 查询职责——start/stop 经 ZMQ daemon 转发的用例随路径一起移除。
"""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import worker.crud as crud
import worker.schemas as schemas
from worker.core_service import WorkerCoreService
from worker.exceptions import WorkerNotFoundException, WorkerOperationException
from worker.orchestrator import WorkerOrchestrator


class TestCoreServiceInProcessIntegration:
    def setup_method(self):
        # WorkerCoreService 和 WorkerOrchestrator 都是 __new__ 单例，必须一起重置
        WorkerCoreService.reset_instance()
        WorkerOrchestrator.reset_instance()

    def teardown_method(self):
        WorkerCoreService.reset_instance()
        WorkerOrchestrator.reset_instance()

    def _mock_db(self, worker_status: str = "stopped"):
        """用假 DB session 替换 get_db，避免测试触碰真实 sqlite。"""
        mock_db = MagicMock()
        fake_worker = MagicMock()
        fake_worker.status = worker_status
        fake_worker.strategy_id = "dual_ma"
        fake_worker.exchange = "binance"
        fake_worker.name = "test"
        mock_db.__enter__.return_value = fake_worker
        mock_db.__exit__.return_value = False
        return mock_db

    def test_start_worker_in_process_success(self):
        """进程内直调：start_strategy 成功后返回 running，pid 记主进程。"""
        service = WorkerCoreService()
        mock_worker_system = MagicMock()
        mock_worker_system.start_strategy = AsyncMock(return_value=True)
        with patch("worker.strategy_manager.worker_system", mock_worker_system):
            result = service._start_worker_in_process(11)
        mock_worker_system.start_strategy.assert_awaited_once_with(11)
        assert result["worker_id"] == 11
        assert result["status"] == "running"
        assert result["pid"] == os.getpid()

    def test_stop_worker_in_process_success(self):
        """进程内直调：stop_strategy 正常完成即返回 stopped（无 pid SIGTERM 兜底场景）。"""
        service = WorkerCoreService()
        mock_worker_system = MagicMock()
        mock_worker_system.stop_strategy = AsyncMock(return_value=True)
        with patch("worker.strategy_manager.worker_system", mock_worker_system):
            result = service._stop_worker_in_process(11)
        mock_worker_system.stop_strategy.assert_awaited_once_with(11)
        assert result["worker_id"] == 11
        assert result["status"] == "stopped"

    def test_stop_worker_idempotent_when_no_runtime(self):
        """DB 有记录但 strategy_manager 无运行时（如重启后从未启动）时幂等返回 stopped。"""
        service = WorkerCoreService()
        mock_worker_system = MagicMock()
        mock_worker_system.stop_strategy = AsyncMock(side_effect=WorkerNotFoundException(11))
        with patch("worker.strategy_manager.worker_system", mock_worker_system):
            result = service._stop_worker_in_process(11)
        assert result["worker_id"] == 11
        assert result["status"] == "stopped"

    def test_get_status_via_orchestrator(self):
        service = WorkerCoreService()
        mock_orch = MagicMock()
        mock_orch.get_worker_info.return_value = MagicMock(is_alive=True)
        mock_orch.send_command_and_wait.return_value = {
            "status": "ok",
            "data": {"worker_id": 11, "status": "running", "pid": 12345},
        }
        with (
            patch.object(WorkerOrchestrator, "get_instance", return_value=mock_orch),
            patch.object(service, "get_db", return_value=self._mock_db()),
        ):
            result = service._get_status_via_orchestrator(11)
            assert result["worker_id"] == 11
            assert result["is_running"] is True

    def test_start_worker_failure_surfaces_registry_error(self):
        """start_strategy 返回 False 时应透传 registry.error_message 真实原因。"""
        service = WorkerCoreService()
        mock_worker_system = MagicMock()
        mock_worker_system.start_strategy = AsyncMock(return_value=False)
        mock_runtime = MagicMock()
        mock_runtime.error_message = "策略启动失败: 未找到策略 'sma_cross'"
        mock_registry = MagicMock()
        mock_registry.get.return_value = mock_runtime
        with (
            patch("worker.strategy_manager.worker_system", mock_worker_system),
            patch("worker.core_service.strategy_registry", mock_registry),
        ):
            with pytest.raises(WorkerOperationException) as exc_info:
                service._start_worker_in_process(11)
        assert "策略启动失败" in exc_info.value.message
        assert "未知原因" not in exc_info.value.message


class TestValidateAndFillStrategy:
    """创建/更新 Worker 时的策略引用校验与回填。"""

    def _create_data(self, strategy_id=None, strategy_name=None):
        return schemas.WorkerCreate(
            name="w1",
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            trading_config={"exchange": "binance"},
        )

    def test_rejects_invalid_strategy_id(self):
        """显式传入的 strategy_id 查不到策略时拒绝创建。"""
        service = WorkerCoreService()
        db = MagicMock()
        data = self._create_data(strategy_id=831237435)
        with patch.object(crud, "find_strategy_by_name_or_id", return_value=None):
            with pytest.raises(WorkerOperationException) as exc_info:
                service._validate_and_fill_strategy(db, data, "创建")
        assert "关联策略不存在" in exc_info.value.message

    def test_fills_name_from_valid_strategy_id(self):
        """strategy_id 命中策略时回填冗余的 strategy_name，防止 id 后续失效。"""
        service = WorkerCoreService()
        db = MagicMock()
        data = self._create_data(strategy_id=5)
        hit = {"id": 5, "name": "test_logging_strategy", "file_name": None}
        with patch.object(crud, "find_strategy_by_name_or_id", return_value=hit) as mock_find:
            service._validate_and_fill_strategy(db, data, "创建")
        mock_find.assert_called_once_with(db, strategy_id=5, strategy_name=None)
        assert data.strategy_id == 5
        assert data.strategy_name == "test_logging_strategy"

    def test_skips_when_no_strategy_reference(self):
        """未关联任何策略的 Worker 允许存在，不做校验。"""
        service = WorkerCoreService()
        db = MagicMock()
        data = self._create_data()
        with patch.object(crud, "find_strategy_by_name_or_id") as mock_find:
            service._validate_and_fill_strategy(db, data, "创建")
        mock_find.assert_not_called()


class TestCoreServicePublicMethods:
    """公开方法 start/stop/get_status 的接入回归测试。

    核心保护: CLI 独立进程从不执行 trading_system.initialize()，
    公开方法走进程内直调路径时绝不能调用 _ensure_initialized()
    （否则抛 RuntimeError，Worker CLI 完全不可用）。
    """

    def setup_method(self):
        WorkerCoreService.reset_instance()
        WorkerOrchestrator.reset_instance()

    def teardown_method(self):
        WorkerCoreService.reset_instance()
        WorkerOrchestrator.reset_instance()

    def _mock_db(self, worker_status: str = "stopped"):
        mock_db = MagicMock()
        fake_worker = MagicMock()
        fake_worker.status = worker_status
        fake_worker.strategy_id = "dual_ma"
        fake_worker.exchange = "binance"
        fake_worker.name = "test"
        fake_worker.pid = None
        mock_db.__enter__.return_value = fake_worker
        mock_db.__exit__.return_value = False
        return mock_db

    def test_start_worker_works_without_trading_system_init(self):
        service = WorkerCoreService()
        with (
            patch.object(service, "get_db", return_value=self._mock_db()),
            patch.object(
                service,
                "_start_worker_in_process",
                return_value={"worker_id": 11, "status": "running", "pid": 1},
            ) as mock_start,
        ):
            result = service.start_worker(11)
            mock_start.assert_called_once_with(11)
            assert result["status"] == "running"

    def test_stop_worker_works_without_trading_system_init(self):
        service = WorkerCoreService()
        with (
            patch.object(service, "get_db", return_value=self._mock_db()),
            patch.object(
                service,
                "_stop_worker_in_process",
                return_value={"worker_id": 11, "status": "stopped"},
            ) as mock_stop,
        ):
            result = service.stop_worker(11)
            mock_stop.assert_called_once_with(11)
            assert result["status"] == "stopped"

    def test_get_worker_status_prefers_orchestrator(self):
        service = WorkerCoreService()
        with (
            patch.object(service, "get_db", return_value=self._mock_db()),
            patch.object(
                service,
                "_get_status_via_orchestrator",
                return_value={"worker_id": 11, "is_running": True},
            ) as mock_status,
        ):
            result = service.get_worker_status(11)
            mock_status.assert_called_once_with(11)
            assert result["is_running"] is True

    def test_batch_core_writes_final_state(self):
        """批量启动成功后，状态机应从 STARTING 回写为 RUNNING（防中间态卡死）。"""
        from worker.state_guard import BatchOperationResult, WorkerState

        service = WorkerCoreService()
        guard = MagicMock()
        batch_result = BatchOperationResult(total=1, success_ids=[11], results=[])
        guard.batch_transition = AsyncMock(return_value=batch_result)
        guard.transition = MagicMock()
        with (
            patch.object(service, "start_worker", return_value={"worker_id": 11, "status": "running"}),
            patch("worker.worker_state.worker_state_manager.transition", new=AsyncMock()),
        ):
            result = asyncio.run(service._run_batch_core(guard, [11], WorkerState.STARTING, "start"))
        assert 11 in result.success_ids
        guard.transition.assert_called_with(11, WorkerState.RUNNING)

    def test_batch_core_failure_moves_to_failed_and_error_state(self):
        """批量某 Worker 真实操作失败时，应从 success 移入 failed 并回写 ERROR。"""
        from worker.state_guard import BatchOperationResult, WorkerState

        service = WorkerCoreService()
        guard = MagicMock()
        batch_result = BatchOperationResult(total=1, success_ids=[11], results=[])
        guard.batch_transition = AsyncMock(return_value=batch_result)
        guard.transition = MagicMock()
        with (
            patch.object(service, "start_worker", side_effect=RuntimeError("boom")),
            patch("worker.worker_state.worker_state_manager.transition", new=AsyncMock()),
        ):
            result = asyncio.run(service._run_batch_core(guard, [11], WorkerState.STARTING, "start"))
        assert result.success_ids == []
        assert 11 in result.failed_dict
        guard.transition.assert_called_with(11, WorkerState.ERROR)


class TestAsyncLifecycleConvergence:
    """异步生命周期方法的状态机收敛回归测试。

    背景（线上卡死事故）：stop/start 是 create_task fire-and-forget 后台任务，
    同步收尾只直写 DB 不动内存缓存；async_restart_worker 曾用 sleep(1) 赌
    stop 收敛，导致 restart 撞上 stopping 过渡态被永久拒绝。
    """

    def setup_method(self):
        WorkerCoreService.reset_instance()
        WorkerOrchestrator.reset_instance()

    def teardown_method(self):
        WorkerCoreService.reset_instance()
        WorkerOrchestrator.reset_instance()

    def _mock_state_manager(self):
        """整体替换 core_service 持有的状态机单例引用，transition 默认放行。"""
        mock = MagicMock()
        mock.transition = AsyncMock(return_value=True)
        mock.get_state = AsyncMock(return_value=None)
        return mock

    async def _drain_runner(self):
        """让 create_task 的后台 runner 有机会跑完（to_thread 走真实线程池）。"""
        for _ in range(100):
            await asyncio.sleep(0.01)

    @pytest.mark.asyncio
    async def test_async_restart_waits_for_stop_convergence(self):
        """回归：restart 在 stop 返回 stopping 后必须等收敛，再执行 start。"""
        service = WorkerCoreService()
        with (
            patch.object(
                service, "async_stop_worker", AsyncMock(return_value={"worker_id": 11, "status": "stopping"})
            ) as mock_stop,
            patch.object(service, "_wait_for_terminal_state", new=AsyncMock()) as mock_wait,
            patch.object(
                service, "async_start_worker", AsyncMock(return_value={"worker_id": 11, "status": "starting"})
            ) as mock_start,
        ):
            await service.async_restart_worker(11)
        mock_stop.assert_awaited_once_with(11)
        mock_wait.assert_awaited_once_with(11, timeout=15.0)
        mock_start.assert_awaited_once_with(11)

    @pytest.mark.asyncio
    async def test_async_stop_runner_syncs_state_machine(self):
        """回归：stop 后台任务成功后必须向状态机补 transition(stopped)，
        否则缓存停在 stopping 而 DB 已 stopped，Worker 永久卡死。"""
        service = WorkerCoreService()
        mock_sm = self._mock_state_manager()
        with (
            patch("worker.core_service.worker_state_manager", mock_sm),
            patch.object(service, "stop_worker", return_value={"worker_id": 11, "status": "stopped", "via": "zmq"}),
        ):
            result = await service.async_stop_worker(11)
            assert result["status"] == "stopping"
            await self._drain_runner()
        statuses = [c.args[1] for c in mock_sm.transition.await_args_list]
        assert statuses == ["stopping", "stopped"]

    @pytest.mark.asyncio
    async def test_async_start_runner_syncs_state_machine(self):
        """回归：start 后台任务成功后必须向状态机补 transition(running, pid)，
        否则缓存停在 starting，后续停止操作被永久拒绝。"""
        service = WorkerCoreService()
        mock_sm = self._mock_state_manager()
        with (
            patch("worker.core_service.worker_state_manager", mock_sm),
            patch.object(service, "start_worker", return_value={"worker_id": 11, "status": "running", "pid": 12345}),
        ):
            result = await service.async_start_worker(11)
            assert result["status"] == "starting"
            await self._drain_runner()
        calls = mock_sm.transition.await_args_list
        assert calls[0].args == (11, "starting")
        assert calls[1].args == (11, "running")
        assert calls[1].kwargs.get("pid") == 12345

    @pytest.mark.asyncio
    async def test_async_stop_runner_failure_moves_to_error(self):
        """stop 后台任务抛异常时也要回写 error，不能留在 stopping 过渡态。"""
        service = WorkerCoreService()
        mock_sm = self._mock_state_manager()
        with (
            patch("worker.core_service.worker_state_manager", mock_sm),
            patch.object(service, "stop_worker", side_effect=RuntimeError("daemon 无响应")),
        ):
            await service.async_stop_worker(11)
            await self._drain_runner()
        statuses = [c.args[1] for c in mock_sm.transition.await_args_list]
        assert statuses == ["stopping", "error"]
