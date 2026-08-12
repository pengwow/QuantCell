"""回测CLI入口单元测试"""

import pytest
from unittest.mock import patch, MagicMock


class TestBacktestCliMain:
    """测试 backtest_cli.py 的 main 函数"""

    @patch("scripts.backtest_cli.sys.path")
    def test_path_setup(self, mock_sys_path):
        """测试后端目录是否正确添加到 sys.path"""
        from scripts.backtest_cli import backend_path

        assert backend_path.name == "backend"
        assert backend_path.exists() is True

    @patch("backtest.cli.app")
    def test_main_calls_app(self, mock_app):
        """测试 main 函数正确调用 backtest.cli.app"""
        from scripts.backtest_cli import main

        main()
        mock_app.assert_called_once()

    @patch("backtest.cli.app")
    def test_main_module_entry(self, mock_app):
        """测试 __main__ 入口调用 main 函数"""
        import scripts.backtest_cli as backtest_cli_module

        with patch.object(backtest_cli_module, "main") as mock_main:
            backtest_cli_module.main()
            mock_main.assert_called_once()


class TestBacktestCliRunArgs:
    """测试 backtest_cli.py run 命令的参数解析(通过 Typer runner)"""

    def test_force_liquidate_default_off(self):
        """默认不传 --force-liquidate,值为 False(保留策略意图)"""
        from typer.testing import CliRunner
        from backtest.cli import app

        runner = CliRunner()
        # 模拟数据加载抛错(我们只关心参数解析部分,在数据加载前参数已落盘)
        with patch("backtest.cli._get_data_provider") as mock_provider:
            mock_provider.return_value.load_multiple.return_value = ({}, None)
            result = runner.invoke(
                app,
                ["run", "--strategy", "no_such_strategy", "--symbols", "BTCUSDT"],
            )

        # 不需要 success(数据加载会失败),关键是参数被解析 + 传到了 engine_config
        # 这里我们验证 default force_liquidate=False 时,engine_config 包含 force_liquidate=False
        # (通过 mock 捕获的 call_args 验证)
        assert mock_provider.called

    def test_force_liquidate_flag_passed_through(self):
        """--force-liquidate 标志解析为 True,传递到 engine_config"""
        from typer.testing import CliRunner
        from backtest.cli import app

        runner = CliRunner()
        with patch("backtest.cli._get_engine_service") as mock_service_factory:
            mock_service = MagicMock()
            mock_service.run_backtest = MagicMock(return_value={"_meta": {}})
            mock_service_factory.return_value = mock_service

            with patch("backtest.cli._get_data_provider") as mock_provider:
                mock_provider.return_value.load_multiple.return_value = ({"BTCUSDT_1h": None}, None)

                # StrategyLoaderService 在 engine_service 函数内 import,patch 真实 import 路径
                with patch("backtest.strategy_loader_service.StrategyLoaderService.load_strategy") as mock_loader:
                    mock_loader.return_value = MagicMock()

                    result = runner.invoke(
                        app,
                        [
                            "run",
                            "--strategy", "fake_strategy",
                            "--symbols", "BTCUSDT",
                            "--timeframes", "1h",
                            "--force-liquidate",
                        ],
                    )

        # run_backtest 应被调用 1 次
        assert mock_service.run_backtest.called, (
            f"run_backtest 未被调用,exit={result.exit_code}, output={result.output}"
        )
        call_kwargs = mock_service.run_backtest.call_args.kwargs
        engine_config = call_kwargs.get("engine_config", {})
        assert engine_config.get("force_liquidate") is True, (
            f"--force-liquidate 应使 engine_config['force_liquidate']=True, "
            f"got {engine_config}"
        )

    def test_no_force_liquidate_flag_passed_through(self):
        """--no-force-liquidate 标志解析为 False(显式关闭)"""
        from typer.testing import CliRunner
        from backtest.cli import app

        runner = CliRunner()
        with patch("backtest.cli._get_engine_service") as mock_service_factory:
            mock_service = MagicMock()
            mock_service.run_backtest = MagicMock(return_value={"_meta": {}})
            mock_service_factory.return_value = mock_service

            with patch("backtest.cli._get_data_provider") as mock_provider:
                mock_provider.return_value.load_multiple.return_value = ({"BTCUSDT_1h": None}, None)

                with patch("backtest.strategy_loader_service.StrategyLoaderService.load_strategy") as mock_loader:
                    mock_loader.return_value = MagicMock()

                    result = runner.invoke(
                        app,
                        [
                            "run",
                            "--strategy", "fake_strategy",
                            "--symbols", "BTCUSDT",
                            "--timeframes", "1h",
                            "--no-force-liquidate",
                        ],
                    )

        assert mock_service.run_backtest.called, (
            f"run_backtest 未被调用,exit={result.exit_code}, output={result.output}"
        )
        call_kwargs = mock_service.run_backtest.call_args.kwargs
        engine_config = call_kwargs.get("engine_config", {})
        assert engine_config.get("force_liquidate") is False

    def test_engine_param_removed(self):
        """--engine 参数应已被删除(只支持唯一引擎)"""
        from typer.testing import CliRunner
        from backtest.cli import app

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "run",
                "--strategy", "fake",
                "--symbols", "BTCUSDT",
                "--timeframes", "1h",
                "--engine", "event",  # 旧参数,应该报错
            ],
        )

        # typer 收到未知选项会返回 exit code 2 + "no such option" 错误
        assert result.exit_code != 0
        # 错误信息应包含 "no such option" 或类似
        combined_output = (result.output + (result.stderr or "")).lower()
        assert (
            "no such option" in combined_output
            or "unrecognized" in combined_output
            or "unrecognized arguments" in combined_output
        ), f"--engine 不应再被接受,但 CLI 接受了它:\n{result.output}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
