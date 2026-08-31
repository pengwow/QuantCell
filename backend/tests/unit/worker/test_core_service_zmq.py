"""WorkerCoreService 与 WorkerOrchestrator 集成测试。"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from worker.core_service import WorkerCoreService
from worker.orchestrator import WorkerOrchestrator


class TestCoreServiceZmqIntegration:
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

    def test_start_worker_via_orchestrator(self):
        service = WorkerCoreService()
        mock_orch = MagicMock()
        mock_orch.is_connected.return_value = False
        mock_orch.start_worker_process.return_value = 12345
        mock_orch.send_command_and_wait.return_value = {"status": "ok", "data": {"status": "running", "pid": 12345}}
        with (
            patch.object(WorkerOrchestrator, "get_instance", return_value=mock_orch),
            patch.object(service, "get_db", return_value=self._mock_db()),
            patch("worker.core_service.crud.update_worker_status") as mock_update,
        ):
            result = service._start_worker_via_orchestrator(11)
            mock_orch.start_worker_process.assert_called_once_with(11)
            mock_update.assert_called_once()  # DB 状态已写 running
            assert result["worker_id"] == 11
            assert result["status"] == "running"

    def test_stop_worker_via_orchestrator_zmq(self):
        """ZMQ 通道可用时，通过 stop 命令优雅停止。"""
        service = WorkerCoreService()
        mock_orch = MagicMock()
        mock_orch.ensure_transport.return_value = None
        mock_orch.send_command_and_wait.return_value = {"status": "ok", "data": {"stopped": True}}
        with (
            patch.object(WorkerOrchestrator, "get_instance", return_value=mock_orch),
            patch.object(service, "get_db", return_value=self._mock_db()),
            patch("worker.core_service.crud.update_worker_status") as mock_update,
        ):
            result = service._stop_worker_via_orchestrator(11)
            mock_orch.send_command_and_wait.assert_called_once()
            mock_update.assert_called_once()
            assert result["worker_id"] == 11
            assert result["status"] == "stopped"
            assert result["via"] == "zmq"

    def test_stop_worker_via_orchestrator_pid_fallback(self):
        """daemon 无响应时回退读 DB pid 发 SIGTERM。"""
        service = WorkerCoreService()
        mock_orch = MagicMock()
        mock_orch.ensure_transport.return_value = None
        mock_orch.send_command_and_wait.return_value = None  # daemon 无响应
        mock_db = self._mock_db()
        mock_db.__enter__.return_value.pid = 99999  # 不存在的 pid，os.kill 抛 ProcessLookupError
        with (
            patch.object(WorkerOrchestrator, "get_instance", return_value=mock_orch),
            patch.object(service, "get_db", return_value=mock_db),
            patch("worker.core_service.crud.update_worker_status"),
        ):
            result = service._stop_worker_via_orchestrator(11)
            assert result["status"] == "stopped"
            assert result["via"] == "pid_fallback"

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


class TestCoreServicePublicMethods:
    """公开方法 start/stop/get_status 的接入回归测试。

    核心保护: CLI 独立进程从不执行 trading_system.initialize()，
    公开方法走 Orchestrator 路径时绝不能调用 _ensure_initialized()
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
                "_start_worker_via_orchestrator",
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
                "_stop_worker_via_orchestrator",
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
