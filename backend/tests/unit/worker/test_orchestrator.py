"""Worker 编排器测试。"""

import os
import sys
import time
from unittest.mock import MagicMock, patch

import pytest

# tests/unit/worker → backend 需上三级；两级只到 tests/，
# tests/utils/ 会遮蔽真正的 backend/utils，导致 utils.logger 导入失败
backend_path = os.path.join(os.path.dirname(__file__), "..", "..", "..")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from worker.orchestrator import WorkerConnectionInfo, WorkerOrchestrator


class TestWorkerConnectionInfo:
    def test_create_info(self):
        info = WorkerConnectionInfo(
            worker_id=11, pid=12345, connected=True, last_heartbeat=time.time(), status="running"
        )
        assert info.is_alive is True

    def test_is_alive_with_old_heartbeat(self):
        info = WorkerConnectionInfo(
            worker_id=11, pid=12345, connected=True, last_heartbeat=time.time() - 120, status="running"
        )
        assert info.is_alive is False

    def test_is_alive_disconnected(self):
        info = WorkerConnectionInfo(
            worker_id=11, pid=12345, connected=False, last_heartbeat=time.time(), status="stopped"
        )
        assert info.is_alive is False


class TestWorkerOrchestrator:
    def setup_method(self):
        WorkerOrchestrator._instance = None

    def teardown_method(self):
        if WorkerOrchestrator._instance:
            WorkerOrchestrator._instance._running = False
            WorkerOrchestrator._instance.cleanup()
            WorkerOrchestrator._instance = None

    def test_singleton(self):
        o1 = WorkerOrchestrator()
        o2 = WorkerOrchestrator()
        assert o1 is o2

    def test_register_worker(self):
        o = WorkerOrchestrator()
        o._register_worker(11, pid=12345)
        assert o.is_connected(11)
        assert o.get_worker_info(11) is not None

    def test_unregister_worker(self):
        o = WorkerOrchestrator()
        o._register_worker(11, pid=12345)
        o._unregister_worker(11)
        assert not o.is_connected(11)

    def test_update_heartbeat(self):
        o = WorkerOrchestrator()
        o._register_worker(11, pid=12345)
        old_time = time.time() - 100
        o._registry[11].last_heartbeat = old_time
        o._update_heartbeat(11)
        assert o._registry[11].last_heartbeat > old_time

    def test_get_disconnected_workers(self):
        o = WorkerOrchestrator()
        o._register_worker(1, pid=100)
        o._register_worker(2, pid=200)
        o._registry[2].last_heartbeat = time.time() - 120
        disconnected = o._get_disconnected_workers()
        assert 2 in disconnected
        assert 1 not in disconnected

    def test_list_connected_workers(self):
        o = WorkerOrchestrator()
        o._register_worker(1, pid=100)
        o._register_worker(2, pid=200)
        o._unregister_worker(1)
        connected = o.list_connected_workers()
        assert len(connected) == 1
        assert connected[0]["worker_id"] == 2

    def test_check_health(self):
        o = WorkerOrchestrator()
        o._register_worker(1, pid=100)
        o._register_worker(2, pid=200)
        o._registry[2].last_heartbeat = time.time() - 120
        summary = o.check_health()
        assert summary["total"] == 2
        assert summary["disconnected"] == 1
        assert 2 in summary["disconnected_ids"]

    def test_cleanup(self):
        o = WorkerOrchestrator()
        o._register_worker(11, pid=12345)
        o._running = True
        o.cleanup()
        assert o._running is False
        assert len(o._registry) == 0
