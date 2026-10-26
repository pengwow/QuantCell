"""Worker Daemon 测试。"""

import os

import pytest

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
        # payload 收缩契约：orchestrator 心跳处理只消费 pid/status
        assert set(hb["payload"].keys()) == {"pid", "status"}
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


class TestDaemonLifecycleCommands:
    """daemon start 命令已废弃：规则/LLM/RL 统一由进程内 Driver 路径运行。

    stop/status 命令保留（编排清理与 status 查询）；原策略运行时残留
    接口（_PaperAdapter/_emit_strategy_event）已随废码清理删除。
    """

    def test_start_command_rejected_with_explicit_error(self):
        """start 命令不再承载策略执行，直接返回明确 error（不降级、不伪成功）。"""
        daemon = WorkerDaemon(worker_id=11)
        resp = daemon._handle_command({"cmd": "start", "request_id": "r1", "params": {"strategy_name": "dual_ma"}})
        assert resp["status"] == "error"
        assert "daemon 不再承载策略执行" in resp["data"]["error"]
        assert daemon._running is False
        daemon.cleanup()
