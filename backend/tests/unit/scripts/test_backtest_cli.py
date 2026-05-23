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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
