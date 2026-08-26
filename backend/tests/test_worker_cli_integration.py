"""Worker CLI 集成测试 — 使用 typer CliRunner 测试所有命令

Mock WorkerCoreService 实例，验证 CLI 命令的输入/输出行为。
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

runner = CliRunner()


def _mock_service():
    """创建一个配置好的 mock WorkerCoreService"""
    svc = MagicMock()
    svc.get_worker_count.return_value = 0
    svc.list_workers.return_value = {"items": [], "total": 0, "page": 1, "page_size": 100}
    svc.get_worker.return_value = {"id": 1, "name": "test", "status": "stopped", "strategy_id": "s1"}
    svc.get_worker_status.return_value = {"db_status": "stopped", "runtime_status": None, "is_running": False}
    svc.create_worker.return_value = {"id": 1, "name": "test_worker"}
    svc.start_worker.return_value = {"worker_id": 1, "status": "running"}
    svc.stop_worker.return_value = {"worker_id": 1, "status": "stopped"}
    svc.restart_worker.return_value = {"worker_id": 1, "status": "running"}
    svc.get_worker_logs.return_value = {"items": [], "total": 0}
    svc.clear_worker_logs.return_value = {"deleted_count": 0}
    svc.get_worker_trades.return_value = {"items": [], "total": 0}
    svc.get_worker_orders.return_value = {"items": [], "total": 0}
    svc.get_worker_stats.return_value = {"total_workers": 0}
    svc.get_worker_performance.return_value = []
    return svc


class TestWorkerSummary:
    """测试 summary 命令"""

    def test_no_workers(self):
        """无 Worker 时显示 '暂无 Worker'"""
        svc = _mock_service()
        svc.get_worker_count.return_value = 0
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["summary"])
            assert result.exit_code == 0
            assert "暂无 Worker" in result.output

    def test_with_workers(self):
        """有 Worker 时显示统计"""
        svc = _mock_service()
        svc.get_worker_count.return_value = 3
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["summary"])
            assert result.exit_code == 0
            assert "Worker 总数: 3" in result.output

    def test_connection_error(self):
        """服务调用失败"""
        svc = _mock_service()
        svc.get_worker_count.side_effect = RuntimeError("Connection refused")
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["summary"])
            assert result.exit_code != 0


class TestWorkerCreate:
    """测试 create 命令"""

    def test_create_success(self):
        """创建 Worker 成功"""
        svc = _mock_service()
        svc.create_worker.return_value = {"id": 1, "name": "test_worker"}
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["create", "--name", "test_worker", "--strategy-id", "1"])
            assert result.exit_code == 0
            assert "test_worker" in result.output
            assert "已创建" in result.output

    def test_create_with_symbol(self):
        """创建 Worker 带交易对"""
        svc = _mock_service()
        svc.create_worker.return_value = {"id": 1, "name": "btc_worker"}
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["create", "--name", "btc_worker", "--strategy-id", "1", "--symbol", "BTCUSDT"])
            assert result.exit_code == 0
            assert "已创建" in result.output

    def test_create_missing_name(self):
        """缺少 --name 应报错"""
        from cli.worker import app

        result = runner.invoke(app, ["create", "--strategy-id", "1"])
        assert result.exit_code != 0

    def test_create_missing_strategy_id(self):
        """缺少 --strategy-id 应报错"""
        from cli.worker import app

        result = runner.invoke(app, ["create", "--name", "test"])
        assert result.exit_code != 0

    def test_create_default_exchange(self):
        """默认交易所为 binance"""
        svc = _mock_service()
        svc.create_worker.return_value = {"id": 1, "name": "worker"}
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["create", "--name", "worker", "--strategy-id", "1"])
            assert result.exit_code == 0
            call_data = svc.create_worker.call_args[0][0]
            assert call_data["exchange"] == "binance"

    def test_create_server_error(self):
        """服务端错误"""
        svc = _mock_service()
        svc.create_worker.side_effect = RuntimeError("Server error")
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["create", "--name", "test", "--strategy-id", "1"])
            assert result.exit_code != 0


class TestWorkerCRUD:
    """测试 Worker 增删改查命令"""

    def test_start_success(self):
        """启动 Worker"""
        svc = _mock_service()
        svc.get_worker_status.return_value = {"is_running": False}
        svc.start_worker.return_value = {"status": "running"}
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["start", "1"])
            assert result.exit_code == 0

    def test_start_already_running(self):
        """启动已在运行的 Worker"""
        svc = _mock_service()
        svc.get_worker_status.return_value = {"is_running": True}
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["start", "1"])
            assert result.exit_code == 0
            assert "正在运行中" in result.output

    def test_stop_success(self):
        svc = _mock_service()
        svc.stop_worker.return_value = {"status": "stopped"}
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["stop", "1"])
            assert result.exit_code == 0

    def test_restart_success(self):
        svc = _mock_service()
        svc.restart_worker.return_value = {"status": "running"}
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["restart", "1"])
            assert result.exit_code == 0

    def test_delete_success(self):
        """删除 Worker"""
        svc = _mock_service()
        svc.get_worker.return_value = {"id": 1, "name": "test"}
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["delete", "1", "--yes"])
            assert result.exit_code == 0

    def test_delete_not_found(self):
        """删除不存在的 Worker"""
        from worker.core_service import WorkerNotFoundError

        svc = _mock_service()
        svc.get_worker.side_effect = WorkerNotFoundError(999)
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["delete", "999", "--yes"])
            assert result.exit_code != 0

    def test_list_workers(self):
        workers = [
            {"id": 1, "name": "w1", "status": "running", "strategy_id": "s1"},
            {"id": 2, "name": "w2", "status": "stopped", "strategy_id": "s2"},
        ]
        svc = _mock_service()
        svc.list_workers.return_value = {"items": workers, "total": 2}
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["list-workers"])
            assert result.exit_code == 0
            assert "w1" in result.output
            assert "w2" in result.output

    def test_list_empty(self):
        svc = _mock_service()
        svc.list_workers.return_value = {"items": [], "total": 0}
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["list-workers"])
            assert result.exit_code == 0
            assert "没有 Worker" in result.output

    def test_list_filter_by_status(self):
        svc = _mock_service()
        svc.list_workers.return_value = {"items": [], "total": 0}
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["list-workers", "--status", "running"])
            assert result.exit_code == 0
            svc.list_workers.assert_called_once_with(status="running", page_size=100)

    def test_status(self):
        svc = _mock_service()
        svc.get_worker.return_value = {
            "id": 1,
            "status": "running",
            "name": "test",
            "strategy_id": "s1",
            "exchange": "binance",
            "symbol": "BTCUSDT",
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

    def test_start_error(self):
        svc = _mock_service()
        svc.get_worker_status.side_effect = RuntimeError("Fail")
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["start", "1"])
            assert result.exit_code != 0

    def test_status_error(self):
        svc = _mock_service()
        svc.get_worker.side_effect = RuntimeError("Fail")
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["status", "1"])
            assert result.exit_code != 0


class TestWorkerMonitoring:
    """测试监控类命令（trades/positions/logs/stats 等）"""

    def test_trades(self):
        svc = _mock_service()
        svc.get_worker_trades.return_value = {
            "items": [
                {"id": "t1", "symbol": "BTCUSDT", "side": "buy", "price": 42000, "quantity": 0.1},
            ],
            "total": 1,
        }
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["trades", "1"])
            assert result.exit_code == 0

    def test_trades_empty(self):
        svc = _mock_service()
        svc.get_worker_trades.return_value = {"items": [], "total": 0}
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["trades", "1"])
            assert result.exit_code == 0
            assert "暂无成交记录" in result.output

    def test_positions(self):
        svc = _mock_service()
        svc.get_worker.return_value = {"id": 1, "name": "test"}
        svc.get_worker_status.return_value = {
            "runtime_status": "running",
            "is_running": True,
        }
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["positions", "1"])
            assert result.exit_code == 0

    def test_positions_empty(self):
        svc = _mock_service()
        svc.get_worker.return_value = {"id": 1, "name": "test"}
        svc.get_worker_status.return_value = {
            "runtime_status": "stopped",
            "is_running": False,
        }
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["positions", "1"])
            assert result.exit_code == 0

    def test_logs_default(self):
        svc = _mock_service()
        svc.get_worker_logs.return_value = {
            "items": [
                {"timestamp": "2024-01-01T00:00:00", "level": "INFO", "message": "Worker started"},
            ],
            "total": 1,
        }
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["logs", "1"])
            assert result.exit_code == 0

    def test_logs_show_path(self):
        svc = _mock_service()
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["logs", "1", "--show-path"])
            assert result.exit_code == 0
            assert "日志目录" in result.output

    def test_logs_clear(self):
        svc = _mock_service()
        svc.clear_worker_logs.return_value = {"deleted_count": 5}
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["logs", "1", "--clear", "--yes"])
            assert result.exit_code == 0

    def test_stats_worker(self):
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

    def test_stats_global(self):
        svc = _mock_service()
        svc.get_worker_stats.return_value = {
            "total_workers": 5,
            "running": 2,
            "stopped": 3,
        }
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["stats"])
            assert result.exit_code == 0

    def test_trading_stats(self):
        svc = _mock_service()
        svc.get_worker_stats.return_value = {
            "worker_id": 1,
            "trades_count": 50,
            "orders_count": 30,
            "status": "running",
        }
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["trading-stats", "1"])
            assert result.exit_code == 0

    def test_pnl_distribution(self):
        svc = _mock_service()
        svc.get_worker_performance.return_value = [
            {"date": "2024-01-01", "pnl": 100.0, "trades": 5},
            {"date": "2024-01-02", "pnl": -50.0, "trades": 3},
        ]
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["pnl-distribution", "1"])
            assert result.exit_code == 0

    def test_trade_history(self):
        svc = _mock_service()
        svc.get_worker_performance.return_value = [
            {"date": "2024-01-01", "pnl": 100.0, "trades": 5},
            {"date": "2024-01-02", "pnl": -50.0, "trades": 3},
        ]
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["trade-history", "1"])
            assert result.exit_code == 0

    def test_orders(self):
        svc = _mock_service()
        svc.get_worker_orders.return_value = {
            "items": [
                {"id": "o1", "side": "buy", "price": 42000, "quantity": 0.1},
            ],
            "total": 1,
        }
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["orders", "1"])
            assert result.exit_code == 0

    def test_orders_empty(self):
        svc = _mock_service()
        svc.get_worker_orders.return_value = {"items": [], "total": 0}
        with patch("cli.worker._service", svc):
            from cli.worker import app

            result = runner.invoke(app, ["orders", "1"])
            assert result.exit_code == 0
            assert "暂无订单" in result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
