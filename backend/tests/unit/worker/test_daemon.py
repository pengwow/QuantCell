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


class TestDaemonStrategyKernel:
    """daemon 策略执行内核：start 命令真实构建 StrategyLoop 并启动。"""

    def test_start_command_launches_strategy_loop(self, monkeypatch):
        """start 命令应加载策略实例、构建 StrategyLoop 并调用 start()。"""
        daemon = WorkerDaemon(worker_id=11)

        started = {}

        class _FakeLoop:
            def __init__(self, adapter, strategy, symbol, event_callback=None):
                self.adapter = adapter
                self.strategy = strategy
                self.symbol = symbol
                self.event_callback = event_callback
                started["loop"] = self

            def start(self):
                started["started"] = True

            def stop(self):
                pass

        # 策略加载器返回 None → 走占位策略降级分支（不依赖真实 strategies 目录）
        monkeypatch.setattr(
            "backtest.strategy_loader_service.StrategyLoaderService.load_event_strategy_multi",
            staticmethod(lambda **kwargs: None),
        )
        monkeypatch.setattr("strategy.loop.StrategyLoop", _FakeLoop)

        resp = daemon._handle_command(
            {"cmd": "start", "request_id": "r1", "params": {"strategy_name": "unknown_strategy"}}
        )
        assert resp["status"] == "ok"
        assert started.get("started") is True
        assert daemon._strategy_loop is not None
        daemon._stop_strategy()
        assert daemon._strategy_loop is None

    def test_start_command_failure_returns_error(self, monkeypatch):
        """StrategyLoop 构建抛异常时，start 命令应返回 error 而非假 running。

        注：策略加载器失败不会走 error（与 StrategyManager 语义一致，降级占位
        策略），此测试验证的是运行时构建失败的兜底路径。
        """
        daemon = WorkerDaemon(worker_id=11)
        monkeypatch.setattr(
            "backtest.strategy_loader_service.StrategyLoaderService.load_event_strategy_multi",
            staticmethod(lambda **kwargs: None),
        )

        class _BoomLoop:
            def __init__(self, **kwargs):
                raise RuntimeError("loop build failed")

        monkeypatch.setattr("strategy.loop.StrategyLoop", _BoomLoop)
        resp = daemon._handle_command({"cmd": "start", "request_id": "r1", "params": {}})
        assert resp["status"] == "error"
        assert "策略启动失败" in resp["data"]["error"]
        assert daemon._running is False
        daemon.cleanup()

    def test_emit_strategy_event_updates_stats_and_forwards(self):
        """订单事件应计数并转发 ZMQ；bar.processed 只更新心跳统计不转发。"""
        daemon = WorkerDaemon(worker_id=11)

        sent = []

        class _FakeTransport:
            def send_event(self, event):
                sent.append(event)

            def close(self, linger=0):
                pass

        daemon._transport = _FakeTransport()

        daemon._emit_strategy_event("order.placed", {"symbol": "BTCUSDT", "side": "Buy"})
        assert daemon._orders_count == 1
        assert len(sent) == 1
        assert sent[0]["event_type"] == "order"

        daemon._emit_strategy_event("bar.processed", {"price": 123.45, "action": "buy"})
        assert daemon._last_price == 123.45
        assert daemon._last_action == "buy"
        assert len(sent) == 1  # bar.processed 不转发

        daemon.cleanup()
