"""Worker Daemon 测试。"""

import os
import sys
import time

import pytest

# 向上三级定位到 backend 目录（tests/unit/worker -> backend），
# 使 `utils`/`worker` 等顶层包可被导入；若仅上两级会落到 tests 目录，
# 其中同名 `utils` 包会遮蔽 backend/utils 导致 utils.logger 导入失败。
backend_path = os.path.join(os.path.dirname(__file__), "..", "..", "..")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from worker.daemon import WorkerDaemon, parse_args


class TestDaemonArgs:
    def test_parse_run_command(self):
        args = parse_args(["run", "--worker-id", "11"])
        assert args.command == "run"
        assert args.worker_id == 11

    def test_parse_run_with_addresses(self):
        args = parse_args(
            [
                "run",
                "--worker-id",
                "5",
                "--event-pull",
                "tcp://127.0.0.1:15558",
                "--cmd-push",
                "tcp://127.0.0.1:15559",
            ]
        )
        assert args.worker_id == 5
        assert args.event_pull == "tcp://127.0.0.1:15558"

    def test_parse_missing_worker_id(self):
        with pytest.raises(SystemExit):
            parse_args(["run"])


class TestWorkerDaemon:
    def test_create_daemon(self):
        daemon = WorkerDaemon(worker_id=11)
        assert daemon.worker_id == 11
        assert daemon.pid == os.getpid()
        daemon.cleanup()

    def test_build_heartbeat(self):
        daemon = WorkerDaemon(worker_id=11)
        hb = daemon._build_heartbeat()
        assert hb["worker_id"] == 11
        assert hb["event_type"] == "heartbeat"
        assert hb["payload"]["pid"] == os.getpid()
        assert hb["payload"]["status"] == "initialized"
        daemon.cleanup()

    def test_handle_ping(self):
        daemon = WorkerDaemon(worker_id=11)
        result = daemon._handle_command({"cmd": "ping", "request_id": "r1"})
        assert result["status"] == "ok"
        assert result["data"]["pong"] is True
        daemon.cleanup()

    def test_handle_status(self):
        daemon = WorkerDaemon(worker_id=11)
        result = daemon._handle_command({"cmd": "status", "request_id": "r1"})
        assert result["status"] == "ok"
        assert result["data"]["worker_id"] == 11
        daemon.cleanup()

    def test_handle_stop(self):
        daemon = WorkerDaemon(worker_id=11)
        daemon._running = True
        result = daemon._handle_command({"cmd": "stop", "request_id": "r1"})
        assert result["status"] == "ok"
        assert daemon._running is False
        daemon.cleanup()

    def test_handle_unknown_cmd(self):
        daemon = WorkerDaemon(worker_id=11)
        result = daemon._handle_command({"cmd": "unknown", "request_id": "r1"})
        assert result["status"] == "error"
        daemon.cleanup()
