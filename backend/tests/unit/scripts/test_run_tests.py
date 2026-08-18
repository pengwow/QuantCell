"""测试运行脚本单元测试"""

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

runner = CliRunner()


class TestRunCommand:
    """测试 run_command 函数"""

    @patch("cli.run.subprocess.run")
    def test_run_command_success(self, mock_subprocess_run):
        """测试命令运行成功"""
        from cli.run import run_command

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_subprocess_run.return_value = mock_result

        result = run_command(["pytest"], verbose=False)
        assert result == 0
        mock_subprocess_run.assert_called_once()

    @patch("cli.run.subprocess.run")
    def test_run_command_failure(self, mock_subprocess_run):
        """测试命令运行失败"""
        from cli.run import run_command

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "测试失败"
        mock_subprocess_run.return_value = mock_result

        result = run_command(["pytest"], verbose=False)
        assert result == 1

    @patch("cli.run.subprocess.run")
    def test_run_command_exception(self, mock_subprocess_run):
        """测试命令运行异常"""
        from cli.run import run_command

        mock_subprocess_run.side_effect = Exception("命令执行错误")

        result = run_command(["pytest"], verbose=False)
        assert result == 1


class TestRunAllTests:
    """测试 run_all_tests 函数"""

    @patch("cli.run.run_command")
    def test_run_all_tests_basic(self, mock_run_command):
        """测试运行所有测试"""
        from cli.run import run_all_tests

        mock_run_command.return_value = 0

        result = run_all_tests(verbose=False, parallel=False)
        assert result == 0
        mock_run_command.assert_called_once()
        call_args = mock_run_command.call_args[0][0]
        assert "uv" in call_args
        assert "pytest" in call_args

    @patch("cli.run.run_command")
    def test_run_all_tests_verbose(self, mock_run_command):
        """测试详细模式运行所有测试"""
        from cli.run import run_all_tests

        mock_run_command.return_value = 0

        result = run_all_tests(verbose=True, parallel=False)
        assert result == 0
        call_args = mock_run_command.call_args[0][0]
        assert "-v" in call_args

    @patch("cli.run.run_command")
    def test_run_all_tests_parallel(self, mock_run_command):
        """测试并行运行所有测试"""
        from cli.run import run_all_tests

        mock_run_command.return_value = 0

        result = run_all_tests(verbose=False, parallel=True)
        assert result == 0
        call_args = mock_run_command.call_args[0][0]
        assert "-n" in call_args
        assert "auto" in call_args


class TestRunUnitTests:
    """测试 run_unit_tests 函数"""

    @patch("cli.run.run_command")
    def test_run_unit_tests(self, mock_run_command):
        """测试运行单元测试"""
        from cli.run import run_unit_tests

        mock_run_command.return_value = 0

        result = run_unit_tests(verbose=False)
        assert result == 0
        call_args = mock_run_command.call_args[0][0]
        assert "tests/unit" in call_args


class TestRunIntegrationTests:
    """测试 run_integration_tests 函数"""

    @patch("cli.run.run_command")
    def test_run_integration_tests(self, mock_run_command):
        """测试运行集成测试"""
        from cli.run import run_integration_tests

        mock_run_command.return_value = 0

        result = run_integration_tests(verbose=False, parallel=False)
        assert result == 0
        call_args = mock_run_command.call_args[0][0]
        assert "tests/integration" in call_args
        assert "integration" in call_args


class TestRunApiTests:
    """测试 run_api_tests 函数"""

    @patch("cli.run.run_command")
    def test_run_api_tests(self, mock_run_command):
        """测试运行API测试"""
        from cli.run import run_api_tests

        mock_run_command.return_value = 0

        result = run_api_tests(verbose=False)
        assert result == 0
        call_args = mock_run_command.call_args[0][0]
        assert "tests/integration/api" in call_args
        assert "api" in call_args


class TestRunCoverageReport:
    """测试 run_coverage_report 函数"""

    @patch("cli.run.run_command")
    def test_run_coverage_report(self, mock_run_command):
        """测试生成覆盖率报告"""
        from cli.run import run_coverage_report

        mock_run_command.return_value = 0

        result = run_coverage_report(verbose=False)
        assert result == 0
        call_args = mock_run_command.call_args[0][0]
        assert "--cov=." in call_args
        assert "--cov-report=term-missing" in call_args
        assert "--cov-report=html" in call_args
        assert "--cov-fail-under=90" in call_args


class TestRunSpecificTest:
    """测试 run_specific_test 函数"""

    @patch("cli.run.run_command")
    def test_run_specific_test(self, mock_run_command):
        """测试运行特定测试文件"""
        from cli.run import run_specific_test

        mock_run_command.return_value = 0

        result = run_specific_test("tests/test_example.py", verbose=False)
        assert result == 0
        call_args = mock_run_command.call_args[0][0]
        assert "tests/test_example.py" in call_args


class TestMainCommand:
    """测试 main 命令"""

    @patch("cli.run.run_all_tests")
    def test_main_default(self, mock_run_all_tests):
        """测试默认运行所有测试"""
        from cli.run import app

        mock_run_all_tests.return_value = 0

        result = runner.invoke(app, [])
        assert result.exit_code == 0
        mock_run_all_tests.assert_called_once()

    @patch("cli.run.run_unit_tests")
    def test_main_unit(self, mock_run_unit_tests):
        """测试仅运行单元测试"""
        from cli.run import app

        mock_run_unit_tests.return_value = 0

        result = runner.invoke(app, ["--unit"])
        assert result.exit_code == 0
        mock_run_unit_tests.assert_called_once()

    @patch("cli.run.run_integration_tests")
    def test_main_integration(self, mock_run_integration_tests):
        """测试仅运行集成测试"""
        from cli.run import app

        mock_run_integration_tests.return_value = 0

        result = runner.invoke(app, ["--integration"])
        assert result.exit_code == 0
        mock_run_integration_tests.assert_called_once()

    @patch("cli.run.run_api_tests")
    def test_main_api(self, mock_run_api_tests):
        """测试仅运行API测试"""
        from cli.run import app

        mock_run_api_tests.return_value = 0

        result = runner.invoke(app, ["--api"])
        assert result.exit_code == 0
        mock_run_api_tests.assert_called_once()

    @patch("cli.run.run_coverage_report")
    def test_main_coverage(self, mock_run_coverage_report):
        """测试生成覆盖率报告"""
        from cli.run import app

        mock_run_coverage_report.return_value = 0

        result = runner.invoke(app, ["--coverage"])
        assert result.exit_code == 0
        mock_run_coverage_report.assert_called_once()

    @patch("cli.run.run_specific_test")
    def test_main_specific_test(self, mock_run_specific_test):
        """测试运行特定测试文件"""
        from cli.run import app

        mock_run_specific_test.return_value = 0

        result = runner.invoke(app, ["tests/test_example.py"])
        assert result.exit_code == 0
        mock_run_specific_test.assert_called_once_with("tests/test_example.py", False)

    @patch("cli.run.get_project_root")
    def test_main_not_in_project_root(self, mock_get_project_root):
        """测试不在项目根目录运行"""
        from cli.run import app

        mock_root = MagicMock()
        mock_root.__truediv__ = MagicMock(return_value=MagicMock(exists=MagicMock(return_value=False)))
        mock_get_project_root.return_value = mock_root

        result = runner.invoke(app, [])
        assert result.exit_code == 1
        assert "未找到 pyproject.toml" in result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
