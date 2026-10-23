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

        # 策略加载器真实返回实例（唯一路径：load_strategy → BaseStrategy）
        # 每 symbol 独立调 load_strategy，保证策略实例不跨 symbol 共享
        load_calls = []

        def _fake_load(**kwargs):
            load_calls.append(kwargs["instrument_ids"])
            return object()

        monkeypatch.setattr(
            "backtest.strategy_loader_service.StrategyLoaderService.load_strategy",
            staticmethod(_fake_load),
        )
        monkeypatch.setattr("strategy.loop.StrategyLoop", _FakeLoop)

        resp = daemon._handle_command({"cmd": "start", "request_id": "r1", "params": {"strategy_name": "dual_ma"}})
        assert resp["status"] == "ok"
        assert started.get("started") is True
        assert len(daemon._strategy_loops) == 1
        daemon._stop_strategy()
        assert daemon._strategy_loops == []
        assert load_calls == [["BTCUSDT"]]  # 未传 symbols 时回退默认标的

    def test_start_command_multi_symbol_creates_one_loop_each(self, monkeypatch):
        """多标的 start 应为每个 symbol 创建独立 strategy 实例 + StrategyLoop。"""
        daemon = WorkerDaemon(worker_id=11)

        class _FakeLoop:
            def __init__(self, adapter, strategy, symbol, event_callback=None):
                self.adapter = adapter
                self.strategy = strategy
                self.symbol = symbol
                self.event_callback = event_callback

            def start(self):
                pass

            def stop(self):
                pass

        # 记录每次加载的策略实例，断言多 symbol 不共享同一实例
        strategy_instances = []

        def _fake_load(**kwargs):
            instance = object()
            strategy_instances.append((kwargs["instrument_ids"][0], instance))
            return instance

        monkeypatch.setattr(
            "backtest.strategy_loader_service.StrategyLoaderService.load_strategy",
            staticmethod(_fake_load),
        )
        monkeypatch.setattr("strategy.loop.StrategyLoop", _FakeLoop)

        symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
        resp = daemon._handle_command(
            {"cmd": "start", "request_id": "r1", "params": {"strategy_name": "dual_ma", "symbols": symbols}}
        )
        assert resp["status"] == "ok"
        # 每 symbol 一个 loop，且 loop 的 symbol 与顺序一致
        assert [loop.symbol for loop in daemon._strategy_loops] == symbols
        # 策略实例互不共享（内部状态不串线）：3 个 symbol 对应 3 个不同实例
        assert len(strategy_instances) == 3
        ids = {id(instance) for _, instance in strategy_instances}
        assert len(ids) == 3

        # 幂等：已运行时再次 start 不重复创建
        resp2 = daemon._handle_command({"cmd": "start", "request_id": "r2", "params": {}})
        assert resp2["status"] == "ok"
        assert resp2["data"]["already_running"] is True
        assert len(daemon._strategy_loops) == 3

        # stop 全部停止并清空
        daemon._stop_strategy()
        assert daemon._strategy_loops == []

    def test_start_command_failure_returns_error(self, monkeypatch):
        """策略加载失败时 start 命令返回 error，不再降级占位策略。"""
        daemon = WorkerDaemon(worker_id=11)

        def _load_boom(**kwargs):
            raise RuntimeError("strategy load failed")

        monkeypatch.setattr(
            "backtest.strategy_loader_service.StrategyLoaderService.load_strategy",
            staticmethod(_load_boom),
        )

        resp = daemon._handle_command({"cmd": "start", "request_id": "r1", "params": {}})
        assert resp["status"] == "error"
        assert "策略启动失败" in resp["data"]["error"]
        assert daemon._running is False
        assert daemon._strategy_loops == []
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
