"""WorkerCoreService 与 WorkerOrchestrator 集成测试。"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# tests/unit/worker → backend 需上三级；两级只到 tests/，
# tests/utils/ 会遮蔽真正的 backend/utils，导致 utils.logger 导入失败
backend_path = os.path.join(os.path.dirname(__file__), "..", "..", "..")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

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

    def test_stop_worker_via_orchestrator(self):
        service = WorkerCoreService()
        mock_orch = MagicMock()
        mock_orch.is_connected.return_value = True
        mock_orch.stop_worker_process.return_value = True
        with (
            patch.object(WorkerOrchestrator, "get_instance", return_value=mock_orch),
            patch.object(service, "get_db", return_value=self._mock_db()),
            patch("worker.core_service.crud.update_worker_status") as mock_update,
        ):
            result = service._stop_worker_via_orchestrator(11)
            mock_orch.stop_worker_process.assert_called_once_with(11)
            mock_update.assert_called_once()
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
