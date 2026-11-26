"""Worker管理CLI单元测试

Mock WorkerCoreService 实例，验证 CLI 命令的输入/输出行为。
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

runner = CliRunner()


def _mock_service(**overrides):
    """创建配置好的 mock WorkerCoreService，支持覆盖特定方法"""
    svc = MagicMock()
    svc.get_worker_count.return_value = 0
    svc.list_workers.return_value = {"items": [], "total": 0}
    svc.get_worker.return_value = {"id": 1, "name": "worker-1", "status": "stopped", "strategy_id": 1}
    svc.get_worker_status.return_value = {"db_status": "stopped", "runtime_status": None, "is_running": False}
    svc.create_worker.return_value = {"id": 1, "name": "worker-1", "status": "created"}
    svc.start_worker.return_value = {"worker_id": 1, "status": "starting"}
    svc.stop_worker.return_value = {"worker_id": 1, "status": "stopped"}
    svc.restart_worker.return_value = {"worker_id": 1, "status": "running"}
    svc.get_worker_logs.return_value = {"items": [], "total": 0}
    svc.clear_worker_logs.return_value = {"deleted_count": 5}
    svc.get_worker_trades.return_value = {"items": [], "total": 0}
    svc.get_worker_orders.return_value = {"items": [], "total": 0}
    svc.get_worker_stats.return_value = {"total_workers": 0}
    # 应用覆盖
    for k, v in overrides.items():
        getattr(svc, k).return_value = v
    return svc


class TestWorkerCliSummary:
    """测试系统摘要命令"""

    def test_summary_success(self):
        """测试获取系统摘要成功"""
        svc = _mock_service(get_worker_count__return_value=2)
        svc.get_worker_count.return_value = 2
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["summary"])
            assert result.exit_code == 0
            assert "2" in result.output

    def test_summary_no_workers(self):
        """测试无Worker的情况"""
        svc = _mock_service()
        svc.get_worker_count.return_value = 0
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["summary"])
            assert result.exit_code == 0
            assert "暂无 Worker" in result.output

    def test_summary_connection_error(self):
        """测试调用失败"""
        svc = _mock_service()
        svc.get_worker_count.side_effect = Exception("连接失败")
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["summary"])
            assert result.exit_code == 1


class TestWorkerCliCreate:
    """测试创建Worker命令"""

    def test_create_success(self):
        """测试创建Worker成功"""
        svc = _mock_service()
        svc.create_worker.return_value = {"id": 1, "name": "worker-1", "status": "created"}
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(
                app,
                ["create", "--name", "worker-1", "--strategy-id", "1", "--exchange", "binance", "--symbol", "BTCUSDT"],
            )
            assert result.exit_code == 0
            assert "worker-1" in result.output

    def test_create_connection_error(self):
        """测试创建Worker失败"""
        svc = _mock_service()
        svc.create_worker.side_effect = Exception("连接失败")
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["create", "--name", "worker-1", "--strategy-id", "1"])
            assert result.exit_code == 1


class TestWorkerCliDelete:
    """测试删除Worker命令"""

    def test_delete_success(self):
        """测试删除Worker成功"""
        svc = _mock_service()
        svc.get_worker.return_value = {"id": 1, "name": "worker-1"}
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["delete", "1", "--yes"])
            assert result.exit_code == 0

    def test_delete_cancel(self):
        """测试取消删除"""
        svc = _mock_service()
        svc.get_worker.return_value = {"id": 1, "name": "worker-1"}
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["delete", "1"], input="n\n")
            assert result.exit_code == 0
            assert "已取消" in result.output

    def test_delete_not_found(self):
        """测试删除不存在的Worker"""
        from worker.core_service import WorkerNotFoundException

        svc = _mock_service()
        svc.get_worker.side_effect = WorkerNotFoundException(1)
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["delete", "1", "--yes"])
            assert result.exit_code == 1
            assert "不存在" in result.output


class TestWorkerCliStart:
    """测试启动Worker命令"""

    def test_start_success(self):
        """测试启动Worker成功"""
        svc = _mock_service()
        svc.get_worker_status.return_value = {"is_running": False}
        svc.start_worker.return_value = {"status": "running"}
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["start", "1"])
            assert result.exit_code == 0

    def test_start_already_running(self):
        """测试启动已在运行的Worker"""
        svc = _mock_service()
        svc.get_worker_status.return_value = {"is_running": True}
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["start", "1"])
            assert result.exit_code == 0
            assert "正在运行中" in result.output

    def test_start_connection_error(self):
        """测试启动失败"""
        svc = _mock_service()
        svc.get_worker_status.side_effect = Exception("连接失败")
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["start", "1"])
            assert result.exit_code == 1


class TestWorkerCliStop:
    """测试停止Worker命令"""

    def test_stop_success(self):
        """测试停止Worker成功"""
        svc = _mock_service()
        svc.stop_worker.return_value = {"status": "stopped"}
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["stop", "1"])
            assert result.exit_code == 0

    def test_stop_force(self):
        """测试强制停止Worker"""
        svc = _mock_service()
        svc.stop_worker.return_value = {"status": "force_stopped"}
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["stop", "1", "--force"])
            assert result.exit_code == 0

    def test_stop_connection_error(self):
        """测试停止失败"""
        svc = _mock_service()
        svc.stop_worker.side_effect = Exception("连接失败")
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["stop", "1"])
            assert result.exit_code == 1


class TestWorkerCliRestart:
    """测试重启Worker命令"""

    def test_restart_success(self):
        """测试重启Worker成功"""
        svc = _mock_service()
        svc.restart_worker.return_value = {"status": "running"}
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["restart", "1"])
            assert result.exit_code == 0
            assert "重启完成" in result.output

    def test_restart_connection_error(self):
        """测试重启失败"""
        svc = _mock_service()
        svc.restart_worker.side_effect = Exception("连接失败")
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["restart", "1"])
            assert result.exit_code == 1


class TestWorkerCliStatus:
    """测试状态查看命令"""

    def test_status_all(self):
        """测试查看所有Worker状态"""
        svc = _mock_service()
        svc.list_workers.return_value = {
            "items": [
                {"id": 1, "name": "worker-1", "status": "running", "strategy_id": 1},
                {"id": 2, "name": "worker-2", "status": "stopped", "strategy_id": 2},
            ],
            "total": 2,
        }
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["status"])
            assert result.exit_code == 0
            assert "worker-1" in result.output

    def test_status_specific(self):
        """测试查看指定Worker状态"""
        svc = _mock_service()
        svc.get_worker.return_value = {
            "id": 1,
            "name": "worker-1",
            "status": "running",
            "strategy_id": 1,
        }
        svc.get_worker_status.return_value = {
            "db_status": "running",
            "runtime_status": "running",
            "is_running": True,
        }
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["status", "1"])
            assert result.exit_code == 0
            assert "worker-1" in result.output

    def test_status_not_found(self):
        """测试查看不存在的Worker"""
        from worker.core_service import WorkerNotFoundException

        svc = _mock_service()
        svc.get_worker.side_effect = WorkerNotFoundException(999)
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["status", "999"])
            assert result.exit_code == 1
            assert "不存在" in result.output


class TestWorkerCliList:
    """测试列表命令"""

    def test_list_all(self):
        """测试列出所有Worker"""
        svc = _mock_service()
        svc.list_workers.return_value = {
            "items": [
                {"id": 1, "name": "worker-1", "status": "running", "strategy_id": 1},
                {"id": 2, "name": "worker-2", "status": "stopped", "strategy_id": 2},
            ],
            "total": 2,
        }
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["list-workers"])
            assert result.exit_code == 0
            assert "worker-1" in result.output

    def test_list_filter_status(self):
        """测试按状态筛选"""
        svc = _mock_service()
        svc.list_workers.return_value = {
            "items": [{"id": 1, "name": "worker-1", "status": "running", "strategy_id": 1}],
            "total": 1,
        }
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["list-workers", "--status", "running"])
            assert result.exit_code == 0
            assert "worker-1" in result.output

    def test_list_empty(self):
        """测试空列表"""
        svc = _mock_service()
        svc.list_workers.return_value = {"items": [], "total": 0}
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["list-workers"])
            assert result.exit_code == 0
            assert "没有 Worker" in result.output


class TestWorkerCliStats:
    """测试统计命令"""

    def test_stats_global(self):
        """测试全局统计"""
        svc = _mock_service()
        svc.get_worker_stats.return_value = {
            "total_workers": 2,
            "running": 1,
            "stopped": 1,
        }
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["stats"])
            assert result.exit_code == 0
            assert "全局统计信息" in result.output

    def test_stats_specific(self):
        """测试指定Worker统计"""
        svc = _mock_service()
        svc.get_worker_stats.return_value = {
            "worker_id": 1,
            "trades_count": 100,
            "orders_count": 50,
            "status": "running",
        }
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["stats", "1"])
            assert result.exit_code == 0
            assert "100" in result.output

    def test_stats_connection_error(self):
        """测试统计失败"""
        svc = _mock_service()
        svc.get_worker_stats.side_effect = Exception("连接失败")
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["stats"])
            assert result.exit_code == 1


class TestWorkerCliLogs:
    """测试日志命令"""

    def test_logs_view(self):
        """测试查看日志"""
        svc = _mock_service()
        svc.get_worker_logs.return_value = {
            "items": [{"timestamp": "2024-01-01T00:00:00", "level": "INFO", "message": "启动Worker"}],
            "total": 1,
        }
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["logs", "1"])
            assert result.exit_code == 0
            assert "启动Worker" in result.output

    def test_logs_empty(self):
        """测试空日志"""
        svc = _mock_service()
        svc.get_worker_logs.return_value = {"items": [], "total": 0}
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["logs", "1", "--lines", "2"])
            assert result.exit_code == 0
            assert "暂无日志" in result.output

    def test_logs_clear(self):
        """测试清理日志"""
        svc = _mock_service()
        svc.clear_worker_logs.return_value = {"deleted_count": 5}
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["logs", "1", "--clear", "--yes"])
            assert result.exit_code == 0
            assert "已清理" in result.output

    def test_logs_path(self):
        """测试显示日志路径"""
        svc = _mock_service()
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["logs", "1", "--show-path"])
            assert result.exit_code == 0
            assert "日志目录" in result.output


class TestWorkerCliTrades:
    """测试成交记录命令"""

    def test_trades_success(self):
        """测试查询成交记录成功"""
        svc = _mock_service()
        svc.get_worker_trades.return_value = {
            "items": [
                {"id": "trade-1", "symbol": "BTCUSDT", "side": "buy", "price": 50000.0, "quantity": 0.1},
            ],
            "total": 1,
        }
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["trades", "1"])
            assert result.exit_code == 0
            assert "trade-1" in result.output

    def test_trades_filter(self):
        """测试筛选成交记录"""
        svc = _mock_service()
        svc.get_worker_trades.return_value = {
            "items": [
                {"id": "trade-1", "symbol": "BTCUSDT", "side": "buy", "price": 50000.0, "quantity": 0.1},
            ],
            "total": 1,
        }
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["trades", "1", "--symbol", "BTCUSDT", "--side", "buy"])
            assert result.exit_code == 0

    def test_trades_empty(self):
        """测试无成交记录"""
        svc = _mock_service()
        svc.get_worker_trades.return_value = {"items": [], "total": 0}
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["trades", "1"])
            assert result.exit_code == 0
            assert "暂无" in result.output


class TestWorkerCliPositions:
    """测试持仓命令"""

    def test_positions_success(self):
        """测试查询持仓成功"""
        svc = _mock_service()
        svc.get_worker.return_value = {"id": 1, "name": "worker-1"}
        svc.get_worker_status.return_value = {"runtime_status": "running", "is_running": True}
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["positions", "1"])
            assert result.exit_code == 0
            assert "运行中" in result.output

    def test_positions_empty(self):
        """测试无持仓"""
        svc = _mock_service()
        svc.get_worker.return_value = {"id": 1, "name": "worker-1"}
        svc.get_worker_status.return_value = {"runtime_status": "stopped", "is_running": False}
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["positions", "1"])
            assert result.exit_code == 0


class TestWorkerCliOrders:
    """测试订单命令"""

    def test_orders_success(self):
        """测试查询订单成功"""
        svc = _mock_service()
        svc.get_worker_orders.return_value = {
            "items": [
                {"id": "order-1", "side": "buy", "event_type": "OrderFilled", "quantity": 0.1, "price": 50000.0},
            ],
            "total": 1,
        }
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["orders", "1"])
            assert result.exit_code == 0
            assert "order-1" in result.output

    def test_orders_filter(self):
        """测试筛选订单"""
        svc = _mock_service()
        svc.get_worker_orders.return_value = {
            "items": [
                {"id": "order-1", "side": "buy", "event_type": "OrderFilled", "quantity": 0.1, "price": 50000.0},
            ],
            "total": 1,
        }
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["orders", "1", "--status", "OrderFilled"])
            assert result.exit_code == 0

    def test_orders_empty(self):
        """测试无订单"""
        svc = _mock_service()
        svc.get_worker_orders.return_value = {"items": [], "total": 0}
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["orders", "1"])
            assert result.exit_code == 0
            assert "暂无" in result.output


class TestWorkerCliTradingStats:
    """测试交易统计命令"""

    def test_trading_stats_success(self):
        """测试交易统计成功"""
        svc = _mock_service()
        svc.get_worker_stats.return_value = {
            "worker_id": 1,
            "trades_count": 100,
            "orders_count": 50,
            "status": "running",
        }
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["trading-stats", "1"])
            assert result.exit_code == 0
            assert "100" in result.output

    def test_trading_stats_empty(self):
        """测试无交易统计"""
        from worker.core_service import WorkerNotFoundException

        svc = _mock_service()
        svc.get_worker_stats.side_effect = WorkerNotFoundException(1)
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["trading-stats", "1"])
            assert result.exit_code == 1


class TestWorkerCliKill:
    """测试强制终止命令（os.kill 必须被 mock，绝不真杀进程）"""

    @staticmethod
    def _svc_with_db():
        svc = _mock_service()
        db = MagicMock()
        svc.get_db.return_value.__enter__.return_value = db
        return svc, db

    def test_kill_success(self, monkeypatch):
        """记录存在且有 pid → 调 os.kill(pid, 9) 并写回 stopped/pid=None"""
        svc, db = self._svc_with_db()
        worker = SimpleNamespace(id=1, pid=4242)
        kills = []
        monkeypatch.setattr("cli.worker.os.kill", lambda pid, sig: kills.append((pid, sig)))
        with (
            patch("cli.worker._service", svc),
            patch("cli.worker.crud.get_worker", return_value=worker),
            patch("cli.worker.crud.update_worker_status") as upd,
        ):
            from cli.worker import app

            result = runner.invoke(app, ["kill", "1"])

        assert result.exit_code == 0
        assert kills == [(4242, 9)]
        assert "已强制终止" in result.output
        assert upd.call_args.args[0] is db
        assert upd.call_args.args[1:] == (1, "stopped")
        assert upd.call_args.kwargs == {"pid": None}

    def test_kill_process_already_gone(self, monkeypatch):
        """进程已不存在 → 诚实提示，仍把 DB 状态收口为 stopped"""

        def gone(pid, sig):
            raise ProcessLookupError

        svc, _db = self._svc_with_db()
        worker = SimpleNamespace(id=1, pid=4242)
        monkeypatch.setattr("cli.worker.os.kill", gone)
        with (
            patch("cli.worker._service", svc),
            patch("cli.worker.crud.get_worker", return_value=worker),
            patch("cli.worker.crud.update_worker_status") as upd,
        ):
            from cli.worker import app

            result = runner.invoke(app, ["kill", "1"])

        assert result.exit_code == 0
        assert "已不存在" in result.output
        assert upd.call_args.args[1:] == (1, "stopped")

    def test_kill_worker_not_found(self, monkeypatch):
        """worker 不存在 → 报错退出，不碰 os.kill / DB 状态"""
        svc, _ = self._svc_with_db()
        kills = []
        monkeypatch.setattr("cli.worker.os.kill", lambda pid, sig: kills.append(pid))
        with (
            patch("cli.worker._service", svc),
            patch("cli.worker.crud.get_worker", return_value=None),
            patch("cli.worker.crud.update_worker_status") as upd,
        ):
            from cli.worker import app

            result = runner.invoke(app, ["kill", "999"])

        assert result.exit_code == 1
        assert "不存在" in result.output
        assert kills == []
        upd.assert_not_called()

    def test_kill_no_pid(self, monkeypatch):
        """有记录但无 pid（未启动）→ 直接返回，不杀、不写状态"""
        svc, _ = self._svc_with_db()
        worker = SimpleNamespace(id=1, pid=None)
        kills = []
        monkeypatch.setattr("cli.worker.os.kill", lambda pid, sig: kills.append(pid))
        with (
            patch("cli.worker._service", svc),
            patch("cli.worker.crud.get_worker", return_value=worker),
            patch("cli.worker.crud.update_worker_status") as upd,
        ):
            from cli.worker import app

            result = runner.invoke(app, ["kill", "1"])

        assert result.exit_code == 0
        assert "无进程 PID" in result.output
        assert kills == []
        upd.assert_not_called()

    def test_kill_permission_error(self, monkeypatch):
        """os.kill 抛非 ProcessLookupError（如权限）→ 错误退出，不误写 stopped"""
        svc, _ = self._svc_with_db()
        worker = SimpleNamespace(id=1, pid=4242)

        def denied(pid, sig):
            raise PermissionError("not permitted")

        monkeypatch.setattr("cli.worker.os.kill", denied)
        with (
            patch("cli.worker._service", svc),
            patch("cli.worker.crud.get_worker", return_value=worker),
            patch("cli.worker.crud.update_worker_status") as upd,
        ):
            from cli.worker import app

            result = runner.invoke(app, ["kill", "1"])

        assert result.exit_code == 1
        assert "错误" in result.output
        upd.assert_not_called()


class TestWorkerCliArchive:
    """测试 journal 归档命令（tmp 目录造文件，无 --yes 时零移动）"""

    @staticmethod
    def _env(tmp_path, monkeypatch):
        monkeypatch.setenv("QUANTCELL_DATA_DIR", str(tmp_path / "data"))
        live = tmp_path / "data" / "live"
        live.mkdir(parents=True)
        (live / "worker_5.jsonl").write_text('{"t":1}\n', encoding="utf-8")
        (live / "worker_5.reconcile.json").write_text("{}", encoding="utf-8")
        return live

    def test_archive_cancel_moves_nothing(self, tmp_path, monkeypatch):
        """无 --yes 且确认拒绝 → 服务未被调用、文件原地不动"""
        live = self._env(tmp_path, monkeypatch)
        svc = _mock_service()
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["archive", "5"], input="n\n")

        assert result.exit_code == 0
        assert "已取消" in result.output
        svc.archive_worker_journal.assert_not_called()
        assert (live / "worker_5.jsonl").is_file()
        assert not (live / "archive").exists()

    def test_archive_worker_not_found(self, tmp_path, monkeypatch):
        """worker 不存在 → 报错退出，零移动"""
        from worker.core_service import WorkerNotFoundException

        live = self._env(tmp_path, monkeypatch)
        svc = _mock_service()
        svc.get_worker.side_effect = WorkerNotFoundException(5)
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["archive", "5", "--yes"])

        assert result.exit_code == 1
        assert "不存在" in result.output
        svc.archive_worker_journal.assert_not_called()
        assert (live / "worker_5.jsonl").is_file()

    def test_archive_confirmed_moves_files_and_lists_paths(self, tmp_path, monkeypatch):
        """--yes → 真实移动到 archive/ 并逐文件打印 from -> to"""
        live = self._env(tmp_path, monkeypatch)
        svc = _mock_service()

        def real_archive(worker_id):
            # 调被测的真实文件移动实现（不构造 StrategyManager，避开重装配）
            from worker.strategy_manager import StrategyManager

            manager = object.__new__(StrategyManager)
            return {"worker_id": worker_id, "archived": manager.archive_journal_files(worker_id)}

        svc.archive_worker_journal.side_effect = real_archive
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["archive", "5", "--yes"])

        assert result.exit_code == 0
        assert result.output.count("moved:") == 2
        assert str(live / "worker_5.jsonl") in result.output
        assert str(live / "worker_5.reconcile.json") in result.output
        assert not (live / "worker_5.jsonl").exists()
        assert not (live / "worker_5.reconcile.json").exists()
        archived = list((live / "archive").iterdir())
        assert len(archived) == 2
        assert "已归档（2 个文件）" in result.output

    def test_archive_no_files_reports_error(self, tmp_path, monkeypatch):
        """journal 不存在 → 服务异常走统一错误分支（exit 1）"""
        monkeypatch.setenv("QUANTCELL_DATA_DIR", str(tmp_path / "empty"))
        svc = _mock_service()

        def real_archive(worker_id):
            from worker.strategy_manager import StrategyManager

            manager = object.__new__(StrategyManager)
            return manager.archive_journal_files(worker_id)

        svc.archive_worker_journal.side_effect = real_archive
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["archive", "5", "--yes"])

        assert result.exit_code == 1
        assert "错误" in result.output


class TestWorkerCliLogsClearCancel:
    """补 logs --clear 的取消分支（--yes 已有覆盖）"""

    def test_logs_clear_cancel(self):
        """确认拒绝 → 已取消，不调用清理服务"""
        svc = _mock_service()
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["logs", "1", "--clear"], input="n\n")

        assert result.exit_code == 0
        assert "已取消" in result.output
        svc.clear_worker_logs.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
