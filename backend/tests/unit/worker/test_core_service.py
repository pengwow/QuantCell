"""WorkerCoreService 单元测试：启停、状态查询、策略引用校验与批量内核。

start/stop 为进程内直调（worker_system）；原 ZMQ daemon 编排层已删除，
状态收口统一走 worker_state_manager（DB 事实源 + 缓存自愈）。
"""

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import worker.crud as crud
import worker.schemas as schemas
from worker.core_service import WorkerCoreService
from worker.exceptions import WorkerNotFoundException, WorkerOperationException


class TestCoreServiceInProcessIntegration:
    def setup_method(self):
        # WorkerCoreService 是 __new__ 单例，测试间必须重置
        WorkerCoreService.reset_instance()

    def teardown_method(self):
        WorkerCoreService.reset_instance()

    def _mock_db(self, worker_status: str = "stopped"):
        """用假 DB session 替换 get_db，避免测试触碰真实 sqlite。"""
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

    def test_start_worker_in_process_success(self):
        """进程内直调：start_strategy 成功后返回 running，pid 记主进程。"""
        service = WorkerCoreService()
        mock_worker_system = MagicMock()
        mock_worker_system.start_strategy = AsyncMock(return_value=True)
        with patch("worker.strategy_manager.worker_system", mock_worker_system):
            result = service._start_worker_in_process(11)
        # ref_price 为启动参考价（价格计划固化），_start_worker_in_process 恒透传给 start_strategy
        mock_worker_system.start_strategy.assert_awaited_once_with(11, ref_price=None)
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

    核心保护: 公开方法走进程内直调路径时绝不能调用 _ensure_initialized()
    （否则 Worker CLI 独立进程直接抛 RuntimeError，完全不可用）。
    """

    def setup_method(self):
        WorkerCoreService.reset_instance()

    def teardown_method(self):
        WorkerCoreService.reset_instance()

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
            # ref_price 显式透传（缺省 None → 计划落 pending）
            mock_start.assert_called_once_with(11, ref_price=None)
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

    def test_get_worker_status_reads_registry_runtime(self):
        """registry 有运行时记录 → 直接读 runtime 状态，is_running 取 runtime。"""
        service = WorkerCoreService()
        runtime = MagicMock()
        runtime.status = "running"
        runtime.is_running = True
        runtime.started_at = "2026-01-01T00:00:00"
        runtime.stopped_at = None
        runtime.error_message = None
        mock_registry = MagicMock()
        mock_registry.get.return_value = runtime
        with (
            patch.object(service, "get_db", return_value=self._mock_db("running")),
            patch("worker.core_service.strategy_registry", mock_registry),
        ):
            result = service.get_worker_status(11)
        assert result["is_running"] is True
        assert result["runtime_status"] == "running"

    def test_get_worker_status_falls_back_to_db_without_runtime(self):
        """registry 无记录（如服务重启后未重新拉起）→ 回退 DB 视图并说明原因。"""
        service = WorkerCoreService()
        mock_registry = MagicMock()
        mock_registry.get.return_value = None
        with (
            patch.object(service, "get_db", return_value=self._mock_db("stopped")),
            patch("worker.core_service.strategy_registry", mock_registry),
        ):
            result = service.get_worker_status(11)
        assert result["is_running"] is False
        assert result["runtime_status"] is None
        assert "无运行时记录" in result["message"]

    def test_batch_core_writes_final_state(self):
        """批量启动成功后，状态应回写为 running（防中间态卡死）。"""
        from worker.worker_state import WorkerState

        service = WorkerCoreService()
        mock_sm = MagicMock()
        mock_sm.get_state = AsyncMock(return_value=SimpleNamespace(status="stopped"))
        mock_sm.transition = AsyncMock(return_value=True)
        with (
            patch("worker.worker_state.worker_state_manager", mock_sm),
            patch.object(service, "start_worker", return_value={"worker_id": 11, "status": "running"}),
        ):
            result = asyncio.run(service._run_batch_core([11], WorkerState.STARTING, "start"))
        assert result.total == 1
        assert 11 in result.success_ids
        mock_sm.transition.assert_awaited_with(11, "running")

    def test_batch_core_failure_moves_to_failed_and_error_state(self):
        """批量某 Worker 真实操作失败时，应从 success 移入 failed 并回写 error。"""
        from worker.worker_state import WorkerState

        service = WorkerCoreService()
        mock_sm = MagicMock()
        mock_sm.get_state = AsyncMock(return_value=SimpleNamespace(status="stopped"))
        mock_sm.transition = AsyncMock(return_value=True)
        with (
            patch("worker.worker_state.worker_state_manager", mock_sm),
            patch.object(service, "start_worker", side_effect=RuntimeError("boom")),
        ):
            result = asyncio.run(service._run_batch_core([11], WorkerState.STARTING, "start"))
        assert result.success_ids == []
        assert 11 in result.failed_dict
        # 失败回写 error 状态（含原因），防止机器停留在 starting 中间态
        mock_sm.transition.assert_awaited_with(11, "error", error_message="boom")

    def test_batch_core_rejects_invalid_transition(self):
        """预检阶段：DB 状态不允许转换到目标态时应直接拒绝，不触发真实操作。"""
        from worker.worker_state import WorkerState

        service = WorkerCoreService()
        mock_sm = MagicMock()
        # stopped 无法直接转换到 STOPPING（停机要求先 starting/running）
        mock_sm.get_state = AsyncMock(return_value=SimpleNamespace(status="stopped"))
        mock_sm.transition = AsyncMock(return_value=True)
        with (
            patch("worker.worker_state.worker_state_manager", mock_sm),
            patch.object(service, "stop_worker") as mock_stop,
        ):
            result = asyncio.run(service._run_batch_core([11], WorkerState.STOPPING, "stop"))
        assert result.success_ids == []
        assert "非法状态转换" in result.failed_dict[11]
        mock_stop.assert_not_called()


class TestAsyncLifecycleConvergence:
    """异步生命周期方法的状态收敛回归测试。

    背景（线上卡死事故）：stop/start 是 create_task fire-and-forget 后台任务，
    同步收尾只直写 DB 不动内存缓存；async_restart_worker 曾用 sleep(1) 赌
    stop 收敛，导致 restart 撞上 stopping 过渡态被永久拒绝。
    """

    def setup_method(self):
        WorkerCoreService.reset_instance()

    def teardown_method(self):
        WorkerCoreService.reset_instance()

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
    async def test_async_restart_defers_start_to_background(self):
        """回归（2026-11-26 更新契约）：restart 立即返回，「等 stop 收敛 + start」全部后台化。

        旧实现在请求协程里 _wait_for_terminal_state(15s)，前端转圈 15s+ 才恢复；
        现在接口入队 stop 即返（毫秒级），编排由后台 runner 接力，失败 transition(error)。
        """
        service = WorkerCoreService()
        with (
            patch.object(service, "async_stop_worker", AsyncMock(return_value={"worker_id": 11, "status": "stopping"})),
            patch.object(service, "_wait_for_terminal_state", new=AsyncMock()) as mock_wait,
            patch.object(
                service, "async_start_worker", AsyncMock(return_value={"worker_id": 11, "status": "starting"})
            ) as mock_start,
        ):
            result = await service.async_restart_worker(11)
            # 立即返回：不等待收敛，此时 start 尚未发起
            assert result["status"] == "stopping"
            mock_start.assert_not_awaited()

            await self._drain_runner()  # 后台 runner 跑完（_spawn_background_task 默认 create_task，真实执行）
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
            patch.object(
                service, "stop_worker", return_value={"worker_id": 11, "status": "stopped", "via": "in_process"}
            ),
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
            patch.object(service, "stop_worker", side_effect=RuntimeError("子进程无响应")),
        ):
            await service.async_stop_worker(11)
            await self._drain_runner()
        statuses = [c.args[1] for c in mock_sm.transition.await_args_list]
        assert statuses == ["stopping", "error"]
