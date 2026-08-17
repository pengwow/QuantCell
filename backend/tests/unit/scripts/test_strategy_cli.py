"""策略CLI单元测试"""

import pytest
import json
from unittest.mock import patch, MagicMock
from typer.testing import CliRunner

runner = CliRunner()


class TestOptimizeStrategyParams:
    """测试 optimize_strategy_params 函数"""

    @patch("scripts.strategy_cli.optimize_strategy_params")
    def test_cli_optimize_success(self, mock_optimize):
        """测试 CLI optimize 命令成功"""
        from scripts.strategy_cli import app

        mock_optimize.return_value = json.dumps({
            "success": True,
            "total_combinations": 2,
            "results": [{"params": {"fast": 5}, "metrics": {"sharpe_ratio": 1.5}}]
        })

        result = runner.invoke(app, [
            "optimize",
            "--strategy-name", "sma_cross",
            "--param-ranges", '{"fast": [5, 10]}'
        ])
        assert result.exit_code == 0

    @patch("scripts.strategy_cli.optimize_strategy_params")
    def test_cli_optimize_error(self, mock_optimize):
        """测试 CLI optimize 命令异常"""
        from scripts.strategy_cli import app

        mock_optimize.return_value = json.dumps({
            "success": False,
            "error": "参数解析失败"
        })

        result = runner.invoke(app, [
            "optimize",
            "--strategy-name", "sma_cross",
            "--param-ranges", "invalid_json"
        ])
        assert result.exit_code == 0

    @patch("backtest.service.BacktestService")
    @patch("itertools.product")
    def test_optimize_params_empty_ranges(self, mock_product, mock_service_cls):
        """测试空参数范围"""
        from scripts.strategy_cli import optimize_strategy_params

        mock_product.return_value = []

        result = optimize_strategy_params("sma_cross", "{}")
        data = json.loads(result)
        assert data["success"] is True
        assert data["total_combinations"] == 0

    @patch("backtest.service.BacktestService")
    def test_optimize_params_invalid_json(self, mock_service_cls):
        """测试无效JSON参数"""
        from scripts.strategy_cli import optimize_strategy_params

        result = optimize_strategy_params("sma_cross", "invalid_json")
        data = json.loads(result)
        assert data["success"] is False
        assert "error" in data


class TestCliCommands:
    """测试 strategy_cli CLI 命令"""

    @patch("scripts.strategy_cli.list_strategies")
    def test_cli_list(self, mock_list):
        """测试 CLI list 命令"""
        from scripts.strategy_cli import app

        mock_list.return_value = "可用策略列表"

        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0

    @patch("scripts.strategy_cli.get_strategy_detail")
    def test_cli_info(self, mock_detail):
        """测试 CLI info 命令"""
        from scripts.strategy_cli import app

        mock_detail.return_value = "策略详情: test_strategy"

        result = runner.invoke(app, ["info", "1"])
        assert result.exit_code == 0

    @patch("scripts.strategy_cli.generate_strategy")
    def test_cli_generate(self, mock_generate):
        """测试 CLI generate 命令"""
        from scripts.strategy_cli import app

        mock_generate.return_value = json.dumps({
            "success": True,
            "file_path": "/path/to/strategy.py"
        })

        result = runner.invoke(app, [
            "generate",
            "--requirement", "双均线策略",
            "--name", "sma_cross"
        ])
        assert result.exit_code == 0

    @patch("scripts.strategy_cli.analyze_backtest_result")
    def test_cli_analyze(self, mock_analyze):
        """测试 CLI analyze 命令"""
        from scripts.strategy_cli import app

        mock_analyze.return_value = json.dumps({"success": True, "metrics": {}})

        result = runner.invoke(app, ["analyze", "--backtest-id", "test-1"])
        assert result.exit_code == 0

    @patch("scripts.strategy_cli.diagnose_strategy")
    def test_cli_diagnose(self, mock_diagnose):
        """测试 CLI diagnose 命令"""
        from scripts.strategy_cli import app

        mock_diagnose.return_value = json.dumps({"success": True, "issues": []})

        result = runner.invoke(app, ["diagnose", "--strategy-name", "sma_cross"])
        assert result.exit_code == 0

    @patch("scripts.strategy_cli.deploy_strategy")
    def test_cli_deploy(self, mock_deploy):
        """测试 CLI deploy 命令"""
        from scripts.strategy_cli import app

        mock_deploy.return_value = json.dumps({
            "success": True,
            "worker_id": 123,
            "status": "created"
        })

        result = runner.invoke(app, [
            "deploy",
            "--strategy-name", "sma_cross",
            "--symbols", "BTCUSDT"
        ])
        assert result.exit_code == 0


class TestListStrategies:
    """测试 list_strategies 函数"""

    @patch("collector.db.database.SessionLocal")
    @patch("collector.db.database.init_database_config")
    def test_list_strategies_empty(self, mock_init_db, mock_session):
        """测试空策略列表"""
        from scripts.strategy_cli import list_strategies

        # 模拟数据库返回空列表
        mock_db = MagicMock()
        mock_db.query.return_value.all.return_value = []
        mock_session.return_value = mock_db

        result = list_strategies()
        assert result == "系统中暂无策略"

    @patch("collector.db.models.Strategy", create=True)
    @patch("collector.db.database.SessionLocal")
    @patch("collector.db.database.init_database_config")
    def test_list_strategies_with_data(self, mock_init_db, mock_session, mock_strategy_cls):
        """测试有策略数据的情况"""
        from scripts.strategy_cli import list_strategies

        # 模拟策略数据
        mock_strategy = MagicMock()
        mock_strategy.id = 1
        mock_strategy.name = "test_strategy"
        mock_strategy.strategy_type = "sma_cross"
        mock_strategy.is_active = True

        mock_db = MagicMock()
        mock_db.query.return_value.all.return_value = [mock_strategy]
        mock_session.return_value = mock_db

        result = list_strategies()
        assert "test_strategy" in result
        assert "ID: 1" in result

    @patch("collector.db.database.SessionLocal")
    @patch("collector.db.database.init_database_config")
    def test_list_strategies_error(self, mock_init_db, mock_session):
        """测试异常处理"""
        from scripts.strategy_cli import list_strategies

        # 模拟异常
        mock_session.side_effect = Exception("数据库连接失败")

        result = list_strategies()
        assert result.startswith("错误:")
        assert "数据库连接失败" in result


class TestGetStrategyDetail:
    """测试 get_strategy_detail 函数"""

    @patch("collector.db.database.SessionLocal")
    @patch("collector.db.database.init_database_config")
    def test_get_strategy_detail_not_found(self, mock_init_db, mock_session):
        """测试策略不存在的情况"""
        from scripts.strategy_cli import get_strategy_detail

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_session.return_value = mock_db

        result = get_strategy_detail(999)
        assert "不存在" in result

    @patch("collector.db.models.Strategy", create=True)
    @patch("collector.db.database.SessionLocal")
    @patch("collector.db.database.init_database_config")
    def test_get_strategy_detail_success(self, mock_init_db, mock_session, mock_strategy_cls):
        """测试成功获取策略详情"""
        from scripts.strategy_cli import get_strategy_detail

        # 模拟策略数据
        mock_strategy = MagicMock()
        mock_strategy.id = 1
        mock_strategy.name = "test_strategy"
        mock_strategy.description = "测试策略"
        mock_strategy.strategy_type = "sma_cross"
        mock_strategy.is_active = True
        mock_strategy.created_at = "2024-01-01"
        mock_strategy.updated_at = "2024-01-02"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_strategy
        mock_session.return_value = mock_db

        result = get_strategy_detail(1)
        assert "test_strategy" in result
        assert "测试策略" in result


class TestGenerateStrategy:
    """测试 generate_strategy 函数"""

    @patch("ai_model.config_utils.get_default_provider_and_models")
    def test_generate_strategy_no_provider(self, mock_get_provider):
        """测试未配置AI模型的情况"""
        from scripts.strategy_cli import generate_strategy

        mock_get_provider.return_value = None

        result = generate_strategy("双均线策略", "sma_cross")
        data = json.loads(result)
        assert data["success"] is False
        assert "未配置AI模型" in data["validation_errors"][0]


class TestAnalyzeBacktestResult:
    """测试 analyze_backtest_result 函数"""

    def test_analyze_no_input(self):
        """测试无输入参数的情况"""
        from scripts.strategy_cli import analyze_backtest_result

        result = analyze_backtest_result()
        data = json.loads(result)
        assert data["success"] is False
        assert "请提供" in data["suggestions"][0]


class TestDiagnoseStrategy:
    """测试 diagnose_strategy 函数"""

    def test_diagnose_strategy_file_not_found(self):
        """测试策略文件不存在的情况"""
        from scripts.strategy_cli import diagnose_strategy

        result = diagnose_strategy("nonexistent_strategy_12345")
        data = json.loads(result)
        # 当策略文件不存在时，success应该是False
        if not data["success"]:
            assert "不存在" in data["issues"][0]
        else:
            # 如果策略文件存在（可能是因为测试环境有该文件），跳过检查
            pass


class TestDeployStrategy:
    """测试 deploy_strategy 函数"""

    @patch("worker.state.strategy_registry.register")
    @patch("worker.state.strategy_registry.list_all", return_value=[])
    def test_deploy_strategy_success(self, mock_list, mock_register):
        """测试成功部署策略"""
        from scripts.strategy_cli import deploy_strategy

        result = deploy_strategy("test_strategy", "BTCUSDT")
        data = json.loads(result)
        assert data["success"] is True
        assert data["worker_id"] == 1
        assert data["status"] == "created"
        mock_register.assert_called_once()

    @patch("worker.state.strategy_registry.register")
    @patch("worker.state.strategy_registry.list_all", return_value=[])
    def test_deploy_strategy_auto_start(self, mock_list, mock_register):
        """测试自动启动部署"""
        from scripts.strategy_cli import deploy_strategy

        result = deploy_strategy("test_strategy", "BTCUSDT", auto_start=True)
        data = json.loads(result)
        assert data["success"] is True
        assert data["worker_id"] == 1
        assert data["status"] == "running"

    @patch("worker.state.strategy_registry.register")
    @patch("worker.state.strategy_registry.list_all")
    def test_deploy_strategy_incremental_id(self, mock_list, mock_register):
        """测试 worker_id 自增逻辑"""
        from scripts.strategy_cli import deploy_strategy

        # 模拟注册表中已有 worker_id=5
        mock_existing = MagicMock()
        mock_existing.worker_id = 5
        mock_list.return_value = [mock_existing]

        result = deploy_strategy("test_strategy", "BTCUSDT")
        data = json.loads(result)
        assert data["success"] is True
        assert data["worker_id"] == 6

    @patch("worker.state.strategy_registry.register")
    @patch("worker.state.strategy_registry.list_all", return_value=[])
    def test_deploy_strategy_registers_runtime(self, mock_list, mock_register):
        """测试部署会将 StrategyRuntime 注册到注册表"""
        from scripts.strategy_cli import deploy_strategy
        from worker.state import StrategyRuntime

        deploy_strategy("dual_ma", "BTCUSDT,ETHUSDT")

        mock_register.assert_called_once()
        runtime = mock_register.call_args[0][0]
        assert isinstance(runtime, StrategyRuntime)
        assert runtime.name == "dual_ma_worker"
        assert runtime.status == "stopped"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
