"""策略CLI单元测试"""

import json
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

runner = CliRunner()


def _all_output(result) -> str:
    """CliRunner 的 stdout + stderr（click 8.2+ 默认分离）"""
    return result.output + getattr(result, "stderr", "")


class TestOptimizeStrategyParams:
    """optimize 命令的真实输出契约（命令级否则会分发到 typer 内部，mock 模块属性无效）"""

    def test_cli_optimize_success(self):
        """两档参数 → 两组合，参数与指标原样出现在 stdout JSON"""
        from cli.strategy import app

        result = runner.invoke(
            app,
            [
                "optimize",
                "--strategy-name",
                "sma_cross",
                "--param-ranges",
                '{"fast": [5, 10]}',
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["success"] is True
        assert data["total_combinations"] == 2
        assert [r["params"] for r in data["results"]] == [{"fast": 5}, {"fast": 10}]
        assert [r["metrics"] for r in data["results"]] == [
            {"sharpe_ratio": 0.0},
            {"sharpe_ratio": 0.0},
        ]

    def test_cli_optimize_invalid_json(self):
        """非法 JSON → 命令正常退出但输出 success=False 的具体错误"""
        from cli.strategy import app

        result = runner.invoke(
            app,
            [
                "optimize",
                "--strategy-name",
                "sma_cross",
                "--param-ranges",
                "invalid_json",
            ],
        )
        assert result.exit_code == 0
        assert json.loads(result.stdout) == {
            "success": False,
            "error": "参数范围必须是有效的JSON",
        }

    def test_optimize_params_empty_ranges(self):
        """空候选集（某一维取值为空数组）→ 0 组合，不是 1"""
        from cli.strategy import optimize_strategy_params

        data = json.loads(optimize_strategy_params("sma_cross", '{"fast": []}'))
        assert data == {"success": True, "total_combinations": 0, "results": []}

    def test_optimize_params_invalid_json(self):
        """纯逻辑函数：非法 JSON 返回结构化错误而不抛异常"""
        from cli.strategy import optimize_strategy_params

        data = json.loads(optimize_strategy_params("sma_cross", "invalid_json"))
        assert data == {"success": False, "error": "参数范围必须是有效的JSON"}


class TestCliWiring:
    """命令级真实行为：用法错误由 click 返回 exit 2，不再 mock 命令背后的实现"""

    def test_cli_analyze_no_inputs(self):
        """无任何输入 → 输出可直接消费的提示 JSON"""
        from cli.strategy import app

        result = runner.invoke(app, ["analyze"])
        assert result.exit_code == 0
        assert json.loads(result.stdout) == {
            "success": False,
            "suggestions": ["请提供回测ID、结果文件或结果数据"],
        }

    def test_cli_diagnose_requires_strategy_name(self):
        """缺少必填 --strategy-name → click 用法错误 exit 2"""
        from cli.strategy import app

        result = runner.invoke(app, ["diagnose"])
        assert result.exit_code == 2
        assert "--strategy-name" in _all_output(result)

    def test_cli_deploy_requires_symbols(self):
        """缺少必填 --symbols → click 用法错误 exit 2"""
        from cli.strategy import app

        result = runner.invoke(app, ["deploy", "--strategy-name", "sma_cross"])
        assert result.exit_code == 2
        assert "--symbols" in _all_output(result)


class TestListStrategies:
    """测试 list_strategies 函数"""

    @patch("collector.db.database.SessionLocal")
    @patch("collector.db.database.init_database_config")
    def test_list_strategies_empty(self, mock_init_db, mock_session):
        """测试空策略列表"""
        from cli.strategy import list_strategies

        # 模拟数据库返回空列表
        mock_db = MagicMock()
        mock_db.query.return_value.all.return_value = []
        mock_session.return_value = mock_db

        result = list_strategies()
        assert result == "系统中暂无策略"

    @patch("collector.db.database.SessionLocal")
    @patch("collector.db.database.init_database_config")
    def test_list_strategies_with_data(self, mock_init_db, mock_session):
        """测试有策略数据的情况（CliRunner：真实策略可列出）"""
        from cli.strategy import app

        # 模拟策略数据
        mock_strategy = MagicMock()
        mock_strategy.id = 1
        mock_strategy.name = "test_strategy"
        mock_strategy.strategy_type = "sma_cross"
        mock_strategy.status = "active"

        mock_db = MagicMock()
        mock_db.query.return_value.all.return_value = [mock_strategy]
        mock_session.return_value = mock_db

        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "test_strategy" in result.output
        assert "ID: 1" in result.output

    @patch("collector.db.database.SessionLocal")
    @patch("collector.db.database.init_database_config")
    def test_list_strategies_error(self, mock_init_db, mock_session):
        """测试数据库异常时非零退出"""
        from cli.strategy import app

        # 模拟异常
        mock_session.side_effect = Exception("数据库连接失败")

        result = runner.invoke(app, ["list"])
        assert result.exit_code == 1
        assert "数据库连接失败" in _all_output(result)


class TestGetStrategyDetail:
    """测试 get_strategy_detail 函数"""

    @patch("collector.db.database.SessionLocal")
    @patch("collector.db.database.init_database_config")
    def test_get_strategy_detail_not_found(self, mock_init_db, mock_session):
        """测试策略不存在的情况：非零退出"""
        from cli.strategy import app

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_session.return_value = mock_db

        result = runner.invoke(app, ["info", "999"])
        assert result.exit_code == 1
        assert "不存在" in _all_output(result)

    @patch("collector.db.database.SessionLocal")
    @patch("collector.db.database.init_database_config")
    def test_get_strategy_detail_success(self, mock_init_db, mock_session):
        """测试成功获取策略详情"""
        from cli.strategy import get_strategy_detail

        # 模拟策略数据
        mock_strategy = MagicMock()
        mock_strategy.id = 1
        mock_strategy.name = "test_strategy"
        mock_strategy.description = "测试策略"
        mock_strategy.strategy_type = "sma_cross"
        mock_strategy.status = "active"
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

    @patch("ai.config.config_utils.get_default_provider_and_models")
    def test_generate_strategy_no_provider(self, mock_get_provider):
        """测试未配置AI模型的情况：非零退出且提示可读"""
        from cli.strategy import app

        mock_get_provider.return_value = None

        result = runner.invoke(app, ["generate", "--requirement", "双均线策略", "--name", "sma_cross"])
        assert result.exit_code == 1
        assert "未配置AI模型" in _all_output(result)

    @patch("strategy.service.StrategyService")
    @patch("ai.config.config_utils.get_default_provider_and_models")
    def test_generate_strategy_service_error(self, mock_get_provider, mock_service_cls):
        """底层服务抛错时 CLI 非零退出且信息可读（不真调 LLM）"""
        from cli.strategy import app

        mock_get_provider.return_value = {"provider": {"id": 1}}
        mock_service_cls.return_value.generate_strategy.side_effect = RuntimeError("LLM 调用失败")

        result = runner.invoke(app, ["generate", "--requirement", "双均线策略", "--name", "sma_cross"])
        assert result.exit_code == 1
        assert "LLM 调用失败" in _all_output(result)
        # 未走到保存步骤
        mock_service_cls.return_value.save_strategy.assert_not_called()

    @patch("strategy.service.StrategyService")
    @patch("ai.config.config_utils.get_default_provider_and_models")
    def test_generate_strategy_success(self, mock_get_provider, mock_service_cls, tmp_path):
        """生成成功时用 --name 落位文件名"""
        from cli.strategy import app

        mock_get_provider.return_value = {"provider": {"id": 1}}
        service = mock_service_cls.return_value
        service.strategy_dir = tmp_path
        service.generate_strategy.return_value = {"code": "class Demo: pass", "explanation": ""}

        result = runner.invoke(app, ["generate", "--requirement", "双均线策略", "--name", "sma_cross"])
        assert result.exit_code == 0
        service.save_strategy.assert_called_once_with("sma_cross", "class Demo: pass")
        assert "sma_cross.py" in result.output


class TestAnalyzeBacktestResult:
    """测试 analyze_backtest_result 函数"""

    def test_analyze_no_input(self):
        """测试无输入参数的情况"""
        from cli.strategy import analyze_backtest_result

        result = analyze_backtest_result()
        data = json.loads(result)
        assert data["success"] is False
        assert "请提供" in data["suggestions"][0]


class TestDiagnoseStrategy:
    """测试 diagnose_strategy 函数"""

    def test_diagnose_strategy_file_not_found(self, monkeypatch, tmp_path):
        """策略文件不存在 → failure + 具体 issue 文案"""
        from cli.strategy import diagnose_strategy

        monkeypatch.chdir(tmp_path)

        data = json.loads(diagnose_strategy("nonexistent_strategy_12345"))
        assert data == {
            "success": False,
            "issues": ["策略文件 nonexistent_strategy_12345.py 不存在"],
        }

    def test_diagnose_strategy_file_exists(self, monkeypatch, tmp_path):
        """策略文件存在 → success=True 且无 issue"""
        from cli.strategy import diagnose_strategy

        (tmp_path / "strategies").mkdir()
        (tmp_path / "strategies" / "sma_cross.py").write_text("class Demo: pass", encoding="utf-8")
        monkeypatch.chdir(tmp_path)

        data = json.loads(diagnose_strategy("sma_cross"))
        assert data == {"success": True, "issues": []}


class TestDeployStrategy:
    """测试 deploy_strategy 函数"""

    @patch("worker.state.strategy_registry.register")
    @patch("worker.state.strategy_registry.list_all", return_value=[])
    def test_deploy_strategy_success(self, mock_list, mock_register):
        """测试成功部署策略"""
        from cli.strategy import deploy_strategy

        result = deploy_strategy("test_strategy", "BTCUSDT")
        data = json.loads(result)
        assert data["success"] is True
        assert data["worker_id"] == 1
        assert data["status"] == "created"
        mock_register.assert_called_once()

    @patch("worker.state.strategy_registry.register")
    @patch("worker.state.strategy_registry.list_all", return_value=[])
    def test_deploy_strategy_auto_start(self, mock_list, mock_register):
        """--auto-start 不启动进程：注册成功 + 明确警告 + status=created"""
        from cli.strategy import app

        result = runner.invoke(
            app,
            [
                "deploy",
                "--strategy-name",
                "test_strategy",
                "--symbols",
                "BTCUSDT",
                "--auto-start",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["success"] is True
        assert data["worker_id"] == 1
        assert data["status"] == "created"
        assert "不支持 --auto-start" in _all_output(result)
        mock_register.assert_called_once()

    @patch("worker.state.strategy_registry.register")
    @patch("worker.state.strategy_registry.list_all")
    def test_deploy_strategy_incremental_id(self, mock_list, mock_register):
        """测试 worker_id 自增逻辑"""
        from cli.strategy import deploy_strategy

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
        from cli.strategy import deploy_strategy
        from worker.state import StrategyRuntime

        deploy_strategy("dual_ma", "BTCUSDT,ETHUSDT")

        mock_register.assert_called_once()
        runtime = mock_register.call_args[0][0]
        assert isinstance(runtime, StrategyRuntime)
        assert runtime.name == "dual_ma_worker"
        assert runtime.status == "stopped"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
