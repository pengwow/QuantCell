"""Worker管理CLI单元测试"""

import pytest
import json
from unittest.mock import patch, MagicMock
from typer.testing import CliRunner


runner = CliRunner()


class TestWorkerCliSummary:
    """测试系统摘要命令"""

    @patch("scripts.worker_cli._get")
    def test_summary_success(self, mock_get):
        """测试获取系统摘要成功"""
        from scripts.worker_cli import app

        mock_get.return_value = {
            "total_workers": 2,
            "status_breakdown": {"running": 1, "stopped": 1},
        }

        result = runner.invoke(app, ["summary"])
        assert result.exit_code == 0
        assert "2" in result.output
        assert "running" in result.output

    @patch("scripts.worker_cli._get")
    def test_summary_no_workers(self, mock_get):
        """测试无Worker的情况"""
        from scripts.worker_cli import app

        mock_get.return_value = []

        result = runner.invoke(app, ["summary"])
        assert result.exit_code == 0
        assert "暂无 Worker" in result.output

    @patch("scripts.worker_cli._get")
    def test_summary_connection_error(self, mock_get):
        """测试连接失败"""
        from scripts.worker_cli import app

        mock_get.side_effect = Exception("连接失败")

        result = runner.invoke(app, ["summary"])
        assert result.exit_code == 1


class TestWorkerCliCreate:
    """测试创建Worker命令"""

    @patch("scripts.worker_cli._post")
    def test_create_success(self, mock_post):
        """测试创建Worker成功"""
        from scripts.worker_cli import app

        mock_post.return_value = {
            "id": 1,
            "name": "worker-1",
            "status": "created",
        }

        result = runner.invoke(app, [
            "create",
            "--name", "worker-1",
            "--strategy-id", "1",
            "--exchange", "binance",
            "--symbol", "BTCUSDT",
        ])
        assert result.exit_code == 0
        assert "worker-1" in result.output

    @patch("scripts.worker_cli._post")
    def test_create_connection_error(self, mock_post):
        """测试创建Worker连接失败"""
        from scripts.worker_cli import app

        mock_post.side_effect = Exception("连接失败")

        result = runner.invoke(app, [
            "create",
            "--name", "worker-1",
            "--strategy-id", "1",
        ])
        assert result.exit_code == 1


class TestWorkerCliDelete:
    """测试删除Worker命令"""

    @patch("scripts.worker_cli._get")
    @patch("scripts.worker_cli._delete")
    def test_delete_success(self, mock_delete, mock_get):
        """测试删除Worker成功"""
        from scripts.worker_cli import app

        mock_get.return_value = {"id": 1, "name": "worker-1"}
        mock_delete.return_value = {"status": "deleted"}

        result = runner.invoke(app, ["delete", "1", "--yes"])
        assert result.exit_code == 0

    @patch("scripts.worker_cli._get")
    def test_delete_cancel(self, mock_get):
        """测试取消删除"""
        from scripts.worker_cli import app

        mock_get.return_value = {"id": 1, "name": "worker-1"}

        result = runner.invoke(app, ["delete", "1"], input="n\n")
        assert result.exit_code == 0
        assert "已取消" in result.output

    @patch("scripts.worker_cli._get")
    def test_delete_not_found(self, mock_get):
        """测试删除不存在的Worker"""
        from scripts.worker_cli import app

        mock_get.return_value = None

        result = runner.invoke(app, ["delete", "1", "--yes"])
        assert result.exit_code == 1
        assert "不存在" in result.output


class TestWorkerCliStart:
    """测试启动Worker命令"""

    @patch("scripts.worker_cli._get")
    @patch("scripts.worker_cli._post")
    def test_start_success(self, mock_post, mock_get):
        """测试启动Worker成功"""
        from scripts.worker_cli import app

        mock_get.return_value = {"id": 1, "name": "worker-1", "_state_info": {"status": "stopped"}}
        mock_post.return_value = {"status": "starting", "pid": 1234}

        result = runner.invoke(app, ["start", "1"])
        assert result.exit_code == 0
        assert "启动请求已发送" in result.output

    @patch("scripts.worker_cli._get")
    def test_start_already_running(self, mock_get):
        """测试启动已在运行的Worker"""
        from scripts.worker_cli import app

        mock_get.return_value = {"id": 1, "name": "worker-1", "_state_info": {"status": "running"}}

        result = runner.invoke(app, ["start", "1"])
        assert result.exit_code == 0
        assert "正在运行中" in result.output

    @patch("scripts.worker_cli._get")
    def test_start_connection_error(self, mock_get):
        """测试启动连接失败"""
        from scripts.worker_cli import app

        mock_get.side_effect = Exception("连接失败")

        result = runner.invoke(app, ["start", "1"])
        assert result.exit_code == 1


class TestWorkerCliStop:
    """测试停止Worker命令"""

    @patch("scripts.worker_cli._post")
    def test_stop_success(self, mock_post):
        """测试停止Worker成功"""
        from scripts.worker_cli import app

        mock_post.return_value = {"status": "stopped"}

        result = runner.invoke(app, ["stop", "1"])
        assert result.exit_code == 0

    @patch("scripts.worker_cli._post")
    def test_stop_force(self, mock_post):
        """测试强制停止Worker"""
        from scripts.worker_cli import app

        mock_post.return_value = {"status": "force_stopped"}

        result = runner.invoke(app, ["stop", "1", "--force"])
        assert result.exit_code == 0

    @patch("scripts.worker_cli._post")
    def test_stop_connection_error(self, mock_post):
        """测试停止连接失败"""
        from scripts.worker_cli import app

        mock_post.side_effect = Exception("连接失败")

        result = runner.invoke(app, ["stop", "1"])
        assert result.exit_code == 1


class TestWorkerCliRestart:
    """测试重启Worker命令"""

    @patch("scripts.worker_cli._post")
    def test_restart_success(self, mock_post):
        """测试重启Worker成功"""
        from scripts.worker_cli import app

        mock_post.return_value = {"start_result": {"status": "started", "pid": 1234}}

        result = runner.invoke(app, ["restart", "1"])
        assert result.exit_code == 0
        assert "重启完成" in result.output

    @patch("scripts.worker_cli._post")
    def test_restart_connection_error(self, mock_post):
        """测试重启连接失败"""
        from scripts.worker_cli import app

        mock_post.side_effect = Exception("连接失败")

        result = runner.invoke(app, ["restart", "1"])
        assert result.exit_code == 1


class TestWorkerCliStatus:
    """测试状态查看命令"""

    @patch("scripts.worker_cli._get")
    def test_status_all(self, mock_get):
        """测试查看所有Worker状态"""
        from scripts.worker_cli import app

        mock_get.return_value = [
            {"id": 1, "name": "worker-1", "status": "running", "strategy_id": 1},
            {"id": 2, "name": "worker-2", "status": "stopped", "strategy_id": 2},
        ]

        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "worker-1" in result.output

    @patch("scripts.worker_cli._get")
    def test_status_specific(self, mock_get):
        """测试查看指定Worker状态"""
        from scripts.worker_cli import app

        mock_get.return_value = {
            "id": 1,
            "name": "worker-1",
            "status": "running",
            "strategy_id": 1,
        }

        result = runner.invoke(app, ["status", "1"])
        assert result.exit_code == 0
        assert "worker-1" in result.output

    @patch("scripts.worker_cli._get")
    def test_status_not_found(self, mock_get):
        """测试查看不存在的Worker"""
        from scripts.worker_cli import app

        mock_get.return_value = None

        result = runner.invoke(app, ["status", "999"])
        assert result.exit_code == 1
        assert "不存在" in result.output


class TestWorkerCliList:
    """测试列表命令"""

    @patch("scripts.worker_cli._get")
    def test_list_all(self, mock_get):
        """测试列出所有Worker"""
        from scripts.worker_cli import app

        mock_get.return_value = [
            {"id": 1, "name": "worker-1", "status": "running", "strategy_id": 1},
            {"id": 2, "name": "worker-2", "status": "stopped", "strategy_id": 2},
        ]

        result = runner.invoke(app, ["list-workers"])
        assert result.exit_code == 0
        assert "worker-1" in result.output

    @patch("scripts.worker_cli._get")
    def test_list_filter_status(self, mock_get):
        """测试按状态筛选"""
        from scripts.worker_cli import app

        mock_get.return_value = [
            {"id": 1, "name": "worker-1", "status": "running", "strategy_id": 1},
        ]

        result = runner.invoke(app, ["list-workers", "--status", "running"])
        assert result.exit_code == 0
        assert "worker-1" in result.output

    @patch("scripts.worker_cli._get")
    def test_list_empty(self, mock_get):
        """测试空列表"""
        from scripts.worker_cli import app

        mock_get.return_value = []

        result = runner.invoke(app, ["list-workers"])
        assert result.exit_code == 0
        assert "没有 Worker" in result.output


class TestWorkerCliStats:
    """测试统计命令"""

    @patch("scripts.worker_cli._get")
    def test_stats_global(self, mock_get):
        """测试全局统计"""
        from scripts.worker_cli import app

        mock_get.return_value = [
            {"id": 1, "name": "worker-1", "status": "running"},
            {"id": 2, "name": "worker-2", "status": "stopped"},
        ]

        result = runner.invoke(app, ["stats"])
        assert result.exit_code == 0
        assert "全局统计信息" in result.output

    @patch("scripts.worker_cli._get")
    def test_stats_specific(self, mock_get):
        """测试指定Worker统计"""
        from scripts.worker_cli import app

        mock_get.side_effect = [
            {"total_trades": 100, "win_rate": 65.0, "total_pnl": 5000.0, "profit_factor": 2.0,
             "winning_trades": 65, "losing_trades": 35, "total_profit": 10000.0, "total_loss": -5000.0,
             "largest_profit": 500.0, "largest_loss": -300.0, "average_profit": 153.85, "average_loss": -142.86,
             "total_volume": 1000.0, "total_fees": 100.0, "trading_days": 30, "daily_average_trades": 3.3},
        ]

        result = runner.invoke(app, ["stats", "1"])
        assert result.exit_code == 0
        assert "100" in result.output

    @patch("scripts.worker_cli._get")
    def test_stats_connection_error(self, mock_get):
        """测试统计连接失败"""
        from scripts.worker_cli import app

        mock_get.side_effect = Exception("连接失败")

        result = runner.invoke(app, ["stats"])
        assert result.exit_code == 1


class TestWorkerCliLogs:
    """测试日志命令"""

    @patch("scripts.worker_cli._get")
    def test_logs_view(self, mock_get):
        """测试查看日志"""
        from scripts.worker_cli import app

        mock_get.side_effect = [
            {"total": 1},
            {"items": [{"timestamp": "2024-01-01T00:00:00", "level": "INFO", "message": "启动Worker", "source": "worker"}], "total": 1},
        ]

        result = runner.invoke(app, ["logs", "1"])
        assert result.exit_code == 0
        assert "启动Worker" in result.output

    @patch("scripts.worker_cli._get")
    def test_logs_lines(self, mock_get):
        """测试限制行数"""
        from scripts.worker_cli import app

        mock_get.side_effect = [
            {"total": 0},
            {"items": [], "total": 0},
        ]

        result = runner.invoke(app, ["logs", "1", "--lines", "2"])
        assert result.exit_code == 0
        assert "暂无日志" in result.output

    @patch("scripts.worker_cli._delete")
    def test_logs_clear(self, mock_delete):
        """测试清理日志"""
        from scripts.worker_cli import app

        mock_delete.return_value = {"deleted_count": 5}

        result = runner.invoke(app, ["logs", "1", "--clear", "--yes"])
        assert result.exit_code == 0
        assert "已清理" in result.output

    @patch("scripts.worker_cli._get")
    def test_logs_path(self, mock_get):
        """测试显示日志路径"""
        from scripts.worker_cli import app

        result = runner.invoke(app, ["logs", "1", "--show-path"])
        assert result.exit_code == 0
        assert "日志文件路径" in result.output


class TestWorkerCliTrades:
    """测试成交记录命令"""

    @patch("scripts.worker_cli._get")
    def test_trades_success(self, mock_get):
        """测试查询成交记录成功"""
        from scripts.worker_cli import app

        mock_get.return_value = {
            "items": [
                {"trade_id": "trade-1", "symbol": "BTCUSDT", "side": "buy", "price": 50000.0, "quantity": 0.1, "amount": 5000.0, "order_type": "market", "created_at": "2024-01-01T00:00:00"},
            ],
            "total": 1,
        }

        result = runner.invoke(app, ["trades", "1"])
        assert result.exit_code == 0
        assert "trade-1" in result.output

    @patch("scripts.worker_cli._get")
    def test_trades_filter(self, mock_get):
        """测试筛选成交记录"""
        from scripts.worker_cli import app

        mock_get.return_value = {
            "items": [{"trade_id": "trade-1", "symbol": "BTCUSDT", "side": "buy", "price": 50000.0, "quantity": 0.1, "amount": 5000.0, "order_type": "market", "created_at": "2024-01-01T00:00:00"}],
            "total": 1,
        }

        result = runner.invoke(app, ["trades", "1", "--symbol", "BTCUSDT", "--side", "buy"])
        assert result.exit_code == 0

    @patch("scripts.worker_cli._get")
    def test_trades_empty(self, mock_get):
        """测试无成交记录"""
        from scripts.worker_cli import app

        mock_get.return_value = {"items": [], "total": 0}

        result = runner.invoke(app, ["trades", "1"])
        assert result.exit_code == 0
        assert "暂无" in result.output


class TestWorkerCliPositions:
    """测试持仓命令"""

    @patch("scripts.worker_cli._get")
    def test_positions_success(self, mock_get):
        """测试查询持仓成功"""
        from scripts.worker_cli import app

        mock_get.return_value = {
            "items": [
                {"symbol": "BTCUSDT", "side": "long", "quantity": 0.5, "avg_price": 50000.0, "unrealized_pnl": 100.0},
            ]
        }

        result = runner.invoke(app, ["positions", "1"])
        assert result.exit_code == 0
        assert "BTCUSDT" in result.output

    @patch("scripts.worker_cli._get")
    def test_positions_empty(self, mock_get):
        """测试无持仓"""
        from scripts.worker_cli import app

        mock_get.return_value = {"items": []}

        result = runner.invoke(app, ["positions", "1"])
        assert result.exit_code == 0
        assert "暂无" in result.output


class TestWorkerCliOrders:
    """测试订单命令"""

    @patch("scripts.worker_cli._get")
    def test_orders_success(self, mock_get):
        """测试查询订单成功"""
        from scripts.worker_cli import app

        mock_get.return_value = {
            "items": [
                {"order_id": "order-1", "symbol": "BTCUSDT", "side": "buy", "event_type": "OrderFilled", "quantity": 0.1, "price": 50000.0, "created_at": "2024-01-01T00:00:00"},
            ],
            "total": 1,
        }

        result = runner.invoke(app, ["orders", "1"])
        assert result.exit_code == 0
        assert "order-1" in result.output

    @patch("scripts.worker_cli._get")
    def test_orders_filter(self, mock_get):
        """测试筛选订单"""
        from scripts.worker_cli import app

        mock_get.return_value = {
            "items": [{"order_id": "order-1", "symbol": "BTCUSDT", "side": "buy", "event_type": "OrderFilled", "quantity": 0.1, "price": 50000.0, "created_at": "2024-01-01T00:00:00"}],
            "total": 1,
        }

        result = runner.invoke(app, ["orders", "1", "--status", "OrderFilled"])
        assert result.exit_code == 0

    @patch("scripts.worker_cli._get")
    def test_orders_empty(self, mock_get):
        """测试无订单"""
        from scripts.worker_cli import app

        mock_get.return_value = {"items": [], "total": 0}

        result = runner.invoke(app, ["orders", "1"])
        assert result.exit_code == 0
        assert "暂无" in result.output


class TestWorkerCliTradingStats:
    """测试交易统计命令"""

    @patch("scripts.worker_cli._get")
    def test_trading_stats_success(self, mock_get):
        """测试交易统计成功"""
        from scripts.worker_cli import app

        mock_get.return_value = {
            "total_trades": 100,
            "winning_trades": 65,
            "losing_trades": 35,
            "win_rate": 65.0,
            "total_pnl": 5000.0,
            "profit_factor": 2.0,
            "total_profit": 10000.0,
            "total_loss": -5000.0,
            "largest_profit": 500.0,
            "largest_loss": -300.0,
            "average_profit": 153.85,
            "average_loss": -142.86,
            "total_volume": 1000.0,
            "total_fees": 100.0,
            "trading_days": 30,
            "daily_average_trades": 3.3,
        }

        result = runner.invoke(app, ["trading-stats", "1"])
        assert result.exit_code == 0
        assert "100" in result.output

    @patch("scripts.worker_cli._get")
    def test_trading_stats_empty(self, mock_get):
        """测试无交易统计"""
        from scripts.worker_cli import app

        mock_get.return_value = None

        result = runner.invoke(app, ["trading-stats", "1"])
        assert result.exit_code == 0
        assert "暂无" in result.output


class TestWorkerCliPnlDistribution:
    """测试盈亏分布命令"""

    @patch("scripts.worker_cli._get")
    def test_pnl_distribution_success(self, mock_get):
        """测试盈亏分布成功"""
        from scripts.worker_cli import app

        mock_get.return_value = {
            "bins": [-100, -50, 0, 50, 100],
            "counts": [5, 10, 20, 15, 8],
            "mean": 10.5,
            "median": 5.0,
            "std": 25.3,
        }

        result = runner.invoke(app, ["pnl-distribution", "1"])
        assert result.exit_code == 0
        assert "盈亏分布" in result.output

    @patch("scripts.worker_cli._get")
    def test_pnl_distribution_empty(self, mock_get):
        """测试无盈亏分布"""
        from scripts.worker_cli import app

        mock_get.return_value = None

        result = runner.invoke(app, ["pnl-distribution", "1"])
        assert result.exit_code == 0
        assert "暂无" in result.output


class TestWorkerCliTradeHistory:
    """测试交易历史命令"""

    @patch("scripts.worker_cli._get")
    def test_trade_history_success(self, mock_get):
        """测试交易历史成功"""
        from scripts.worker_cli import app

        mock_get.return_value = {
            "daily": [
                {"date": "2024-01-01", "pnl": 100.0, "trades": 5},
                {"date": "2024-01-02", "pnl": -50.0, "trades": 3},
            ],
        }

        result = runner.invoke(app, ["trade-history", "1"])
        assert result.exit_code == 0
        assert "2024-01-01" in result.output

    @patch("scripts.worker_cli._get")
    def test_trade_history_empty(self, mock_get):
        """测试无交易历史"""
        from scripts.worker_cli import app

        mock_get.return_value = {"daily": []}

        result = runner.invoke(app, ["trade-history", "1"])
        assert result.exit_code == 0
        assert "暂无" in result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
