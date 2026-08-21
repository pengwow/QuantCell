"""Worker CLI 集成测试 — 使用 typer CliRunner 测试所有命令"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

runner = CliRunner()


class TestWorkerSummary:
    """测试 summary 命令"""

    def test_no_workers(self):
        """无 Worker 时显示 '暂无 Worker'"""
        with patch("cli.worker._get", return_value={"total_workers": 0}):
            from cli.worker import app

            result = runner.invoke(app, ["summary"])
            assert result.exit_code == 0
            assert "暂无 Worker" in result.output

    def test_with_workers(self):
        """有 Worker 时显示统计"""
        with patch(
            "cli.worker._get",
            return_value={
                "total_workers": 3,
                "status_breakdown": {"running": 2, "stopped": 1},
            },
        ):
            from cli.worker import app

            result = runner.invoke(app, ["summary"])
            assert result.exit_code == 0
            assert "Worker 总数: 3" in result.output

    def test_connection_error(self):
        """连接失败"""
        with patch("cli.worker._get", side_effect=RuntimeError("Connection refused")):
            from cli.worker import app

            result = runner.invoke(app, ["summary"])
            assert result.exit_code != 0


class TestWorkerCreate:
    """测试 create 命令"""

    def test_create_success(self):
        """创建 Worker 成功"""
        with patch("cli.worker._post", return_value={"id": 1, "name": "test_worker"}):
            from cli.worker import app

            result = runner.invoke(app, ["create", "--name", "test_worker", "--strategy-id", "1"])
            assert result.exit_code == 0
            assert "test_worker" in result.output
            assert "已创建" in result.output

    def test_create_with_symbol(self):
        """创建 Worker 带交易对"""
        with patch("cli.worker._post", return_value={"id": 1, "name": "btc_worker"}):
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
        with patch("cli.worker._post", return_value={"id": 1, "name": "worker"}) as mock:
            from cli.worker import app

            result = runner.invoke(app, ["create", "--name", "worker", "--strategy-id", "1"])
            assert result.exit_code == 0
            call_data = mock.call_args[0][1]
            assert call_data["exchange"] == "binance"

    def test_create_server_error(self):
        """服务端错误"""
        with patch("cli.worker._post", side_effect=RuntimeError("Server error")):
            from cli.worker import app

            result = runner.invoke(app, ["create", "--name", "test", "--strategy-id", "1"])
            assert result.exit_code != 0


class TestWorkerCRUD:
    """测试 Worker 增删改查命令"""

    def test_start_success(self):
        """启动 Worker：先 get 检查存在，再 post 发送启动"""
        with patch(
            "cli.worker._get",
            return_value={
                "id": 1,
                "name": "test",
                "_state_info": {"status": "stopped"},
            },
        ):
            with patch("cli.worker._post", return_value={"status": "running"}):
                from cli.worker import app

                result = runner.invoke(app, ["start", "1"])
                assert result.exit_code == 0

    def test_stop_success(self):
        with patch("cli.worker._post", return_value={"status": "stopped"}):
            from cli.worker import app

            result = runner.invoke(app, ["stop", "1"])
            assert result.exit_code == 0

    def test_restart_success(self):
        with patch("cli.worker._post", return_value={"status": "running"}):
            from cli.worker import app

            result = runner.invoke(app, ["restart", "1"])
            assert result.exit_code == 0

    def test_delete_success(self):
        """删除 Worker"""
        with patch("cli.worker._get", return_value={"id": 1, "name": "test"}):
            with patch("cli.worker._delete", return_value={}):
                from cli.worker import app

                result = runner.invoke(app, ["delete", "1", "--yes"])
                assert result.exit_code == 0

    def test_delete_not_found(self):
        """删除不存在的 Worker"""
        with patch("cli.worker._get", return_value=None):
            from cli.worker import app

            result = runner.invoke(app, ["delete", "999", "--yes"])
            assert result.exit_code != 0

    def test_list_workers(self):
        workers = [
            {"id": 1, "name": "w1", "status": "running", "strategy_id": "s1"},
            {"id": 2, "name": "w2", "status": "stopped", "strategy_id": "s2"},
        ]
        with patch("cli.worker._get", return_value=workers):
            from cli.worker import app

            result = runner.invoke(app, ["list-workers"])
            assert result.exit_code == 0
            assert "w1" in result.output
            assert "w2" in result.output

    def test_list_empty(self):
        with patch("cli.worker._get", return_value=[]):
            from cli.worker import app

            result = runner.invoke(app, ["list-workers"])
            assert result.exit_code == 0
            assert "没有 Worker" in result.output

    def test_list_filter_by_status(self):
        with patch("cli.worker._get", return_value=[]) as mock:
            from cli.worker import app

            result = runner.invoke(app, ["list-workers", "--status", "running"])
            assert result.exit_code == 0
            call_url = mock.call_args[0][0]
            assert "status=running" in call_url

    def test_status(self):
        with patch(
            "cli.worker._get",
            return_value={
                "id": 1,
                "status": "running",
                "name": "test",
                "strategy_id": "s1",
                "exchange": "binance",
                "symbol": "BTCUSDT",
                "uptime": 3600,
                "trades_today": 5,
                "total_pnl": 100.0,
                "unrealized_pnl": 50.0,
                "realized_pnl": 50.0,
                "positions": [],
                "trades": [],
            },
        ):
            from cli.worker import app

            result = runner.invoke(app, ["status", "1"])
            assert result.exit_code == 0

    def test_start_error(self):
        with patch("cli.worker._post", side_effect=RuntimeError("Fail")):
            from cli.worker import app

            result = runner.invoke(app, ["start", "1"])
            assert result.exit_code != 0

    def test_status_error(self):
        with patch("cli.worker._get", side_effect=RuntimeError("Fail")):
            from cli.worker import app

            result = runner.invoke(app, ["status", "1"])
            assert result.exit_code != 0


class TestWorkerMonitoring:
    """测试监控类命令（trades/positions/logs/stats 等）"""

    def test_trades(self):
        with patch(
            "cli.worker._get",
            return_value={
                "items": [
                    {
                        "trade_id": "t1",
                        "symbol": "BTCUSDT",
                        "side": "buy",
                        "price": 42000,
                        "quantity": 0.1,
                        "amount": 4200,
                    },
                ]
            },
        ):
            from cli.worker import app

            result = runner.invoke(app, ["trades", "1"])
            assert result.exit_code == 0

    def test_trades_empty(self):
        with patch("cli.worker._get", return_value={"items": []}):
            from cli.worker import app

            result = runner.invoke(app, ["trades", "1"])
            assert result.exit_code == 0
            assert "暂无成交记录" in result.output

    def test_positions(self):
        with patch(
            "cli.worker._get",
            return_value={
                "items": [
                    {
                        "symbol": "BTCUSDT",
                        "side": "long",
                        "quantity": 0.5,
                        "entry_price": 40000,
                        "mark_price": 42000,
                        "unrealized_pnl": 1000,
                    },
                ]
            },
        ):
            from cli.worker import app

            result = runner.invoke(app, ["positions", "1"])
            assert result.exit_code == 0

    def test_positions_empty(self):
        with patch("cli.worker._get", return_value={"items": []}):
            from cli.worker import app

            result = runner.invoke(app, ["positions", "1"])
            assert result.exit_code == 0
            assert "暂无持仓" in result.output

    def test_logs_default(self):
        """默认显示日志内容"""
        with patch(
            "cli.worker._get",
            return_value={
                "items": [
                    {"timestamp": "2024-01-01T00:00:00", "level": "INFO", "message": "Worker started"},
                ]
            },
        ):
            from cli.worker import app

            result = runner.invoke(app, ["logs", "1"])
            assert result.exit_code == 0

    def test_logs_show_path(self):
        """--show-path 显示日志路径"""
        from cli.worker import app

        result = runner.invoke(app, ["logs", "1", "--show-path"])
        assert result.exit_code == 0
        assert "日志文件路径" in result.output

    def test_logs_clear(self):
        """--clear 清理日志"""
        with patch("cli.worker._delete", return_value={"deleted_count": 5}):
            from cli.worker import app

            result = runner.invoke(app, ["logs", "1", "--clear", "--yes"])
            assert result.exit_code == 0

    def test_stats_worker(self):
        with patch(
            "cli.worker._get",
            return_value={
                "total_trades": 100,
                "win_rate": 0.55,
            },
        ):
            from cli.worker import app

            result = runner.invoke(app, ["stats", "1"])
            assert result.exit_code == 0

    def test_stats_global(self):
        with patch(
            "cli.worker._get",
            return_value=[
                {"id": 1, "name": "w1"},
                {"id": 2, "name": "w2"},
            ],
        ):
            from cli.worker import app

            result = runner.invoke(app, ["stats"])
            assert result.exit_code == 0

    def test_trading_stats(self):
        with patch(
            "cli.worker._get",
            return_value={
                "total_pnl": 2500,
                "total_trades": 50,
                "win_rate": 0.55,
                "sharpe_ratio": 1.5,
                "max_drawdown": 0.1,
                "profit_factor": 2.0,
            },
        ):
            from cli.worker import app

            result = runner.invoke(app, ["trading-stats", "1"])
            assert result.exit_code == 0

    def test_pnl_distribution(self):
        with patch(
            "cli.worker._get",
            return_value={
                "total_profit": 5000,
                "total_loss": -2000,
                "profit_trades": 30,
                "loss_trades": 20,
                "best_trade": 500,
                "worst_trade": -200,
            },
        ):
            from cli.worker import app

            result = runner.invoke(app, ["pnl-distribution", "1"])
            assert result.exit_code == 0

    def test_trade_history(self):
        """trade-history 命令返回 daily 汇总列表"""
        with patch(
            "cli.worker._get",
            return_value={
                "daily": [
                    {"date": "2024-01-01", "pnl": 100.0, "trades": 5},
                    {"date": "2024-01-02", "pnl": -50.0, "trades": 3},
                ],
            },
        ):
            from cli.worker import app

            result = runner.invoke(app, ["trade-history", "1"])
            assert result.exit_code == 0

    def test_orders(self):
        with patch(
            "cli.worker._get",
            return_value={
                "items": [
                    {"order_id": "o1", "side": "buy", "price": 42000, "quantity": 0.1, "status": "filled"},
                ]
            },
        ):
            from cli.worker import app

            result = runner.invoke(app, ["orders", "1"])
            assert result.exit_code == 0

    def test_orders_empty(self):
        with patch("cli.worker._get", return_value={"items": []}):
            from cli.worker import app

            result = runner.invoke(app, ["orders", "1"])
            assert result.exit_code == 0
            assert "暂无订单" in result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
