#!/usr/bin/env python3
"""
CLI 全量测试脚本

覆盖所有 CLI 模块的:
- 功能完整性和正确性
- 命令行参数组合及边界值
- 错误处理机制和异常输入
- 输出结果验证
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CLI_DIR = PROJECT_ROOT / "cli"

# 所有 CLI 模块列表
CLI_MODULES = [
    "worker",
    "strategy",
    "data",
    "tests_cmd",
    "web",
    "account",
    "news",
    "backtest",
    "plugin",
    "agent",
    "rl",
    "market",
    "run",
]


def run_cli(module: str, args: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    """执行 CLI 命令"""
    cmd = [sys.executable, "-m", f"cli.{module}", *args]
    return subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


class TestCLIBasicFunctionality:
    """测试各 CLI 模块的基本功能"""

    @pytest.mark.parametrize("module", CLI_MODULES)
    def test_help_command(self, module):
        """测试所有模块的 --help 命令"""
        result = run_cli(module, ["--help"])
        assert result.returncode == 0, f"{module} --help 失败: {result.stderr}"
        assert "Usage:" in result.stdout or "usage:" in result.stdout.lower(), f"{module} --help 未输出 Usage 信息"

    @pytest.mark.parametrize("module", CLI_MODULES)
    def test_module_loadable(self, module):
        """测试所有模块可正常加载"""
        result = run_cli(module, ["--help"])
        # 排除 migrate 模块（可能没有注册命令）
        if module == "migrate":
            return
        assert result.returncode == 0, f"{module} 模块加载失败: {result.stderr}"


class TestCLIWorker:
    """测试 worker CLI 模块"""

    def test_worker_help(self):
        """测试 worker --help"""
        result = run_cli("worker", ["--help"])
        assert result.returncode == 0
        assert "summary" in result.stdout
        assert "create" in result.stdout
        assert "delete" in result.stdout
        assert "start" in result.stdout
        assert "stop" in result.stdout
        assert "restart" in result.stdout
        assert "status" in result.stdout
        assert "list-workers" in result.stdout
        assert "logs" in result.stdout
        assert "trades" in result.stdout
        assert "positions" in result.stdout
        assert "orders" in result.stdout

    WORKER_SUBCOMMANDS = [
        "create",
        "delete",
        "start",
        "stop",
        "restart",
        "status",
        "list-workers",
        "summary",
        "stats",
        "logs",
        "trades",
        "positions",
        "orders",
        "trading-stats",
        "pnl-distribution",
        "trade-history",
    ]

    @pytest.mark.parametrize("cmd", WORKER_SUBCOMMANDS)
    def test_worker_subcommand_help(self, cmd):
        """测试各子命令的帮助（逐命令参数化：单个 CLI 进程 import 约 3-5s，
        若在一个测试函数内串行 16 个子命令会超过 pytest-timeout 的 30s 上限）"""
        result = run_cli("worker", [cmd, "--help"])
        assert result.returncode == 0, f"worker {cmd} --help 失败: {result.stderr}"

    def test_worker_create_missing_args(self):
        """测试创建 Worker 缺少必填参数"""
        result = run_cli("worker", ["create"])
        # 应该退出码非 0（缺少 --name 和 --strategy-id）
        assert result.returncode != 0, "缺少必填参数时应报错"

    def test_worker_create_missing_name(self):
        """测试创建 Worker 缺少 --name"""
        result = run_cli("worker", ["create", "--strategy-id", "1"])
        assert result.returncode != 0, "缺少 --name 时应报错"

    def test_worker_create_invalid_strategy_id(self):
        """测试创建 Worker 缺少 --strategy-id"""
        result = run_cli("worker", ["create", "--name", "test"])
        assert result.returncode != 0, "缺少 --strategy-id 时应报错"

    def test_worker_start_invalid_id(self):
        """测试启动不存在的 Worker"""
        result = run_cli("worker", ["start", "99999"])
        # 可能因后端未启动而报错，这是预期行为
        assert result.returncode != 0 or "错误" in result.stdout


class TestCLIStrategy:
    """测试 strategy CLI 模块"""

    def test_strategy_help(self):
        """测试 strategy --help"""
        result = run_cli("strategy", ["--help"])
        assert result.returncode == 0
        assert "list" in result.stdout
        assert "info" in result.stdout
        assert "generate" in result.stdout
        assert "analyze" in result.stdout
        assert "diagnose" in result.stdout
        assert "deploy" in result.stdout
        assert "optimize" in result.stdout

    def test_strategy_list(self):
        """测试策略列表命令"""
        result = run_cli("strategy", ["list"])
        assert result.returncode == 0

    def test_strategy_diagnose_missing_strategy(self):
        """测试诊断不存在的策略"""
        result = run_cli("strategy", ["diagnose", "--strategy-name", "nonexistent_strategy_12345"])
        assert result.returncode == 0
        data = json.loads(result.stdout.strip())
        assert data["success"] is False
        assert any("不存在" in issue for issue in data["issues"])

    def test_strategy_diagnose_existing(self):
        """测试诊断现有策略"""
        result = run_cli("strategy", ["diagnose", "--strategy-name", "dual_ma"])
        assert result.returncode == 0
        data = json.loads(result.stdout.strip())
        assert "success" in data

    def test_strategy_deploy_missing_args(self):
        """测试部署缺少必填参数"""
        result = run_cli("strategy", ["deploy"])
        assert result.returncode != 0

    def test_strategy_deploy_missing_strategy_name(self):
        """测试部署缺少 --strategy-name"""
        result = run_cli("strategy", ["deploy", "--symbols", "BTCUSDT"])
        assert result.returncode != 0

    def test_strategy_deploy_missing_symbols(self):
        """测试部署缺少 --symbols"""
        result = run_cli("strategy", ["deploy", "--strategy-name", "dual_ma"])
        assert result.returncode != 0

    def test_strategy_deploy_with_auto_start(self):
        """测试部署并自动启动"""
        result = run_cli(
            "strategy",
            [
                "deploy",
                "--strategy-name",
                "dual_ma",
                "--symbols",
                "BTCUSDT",
                "--auto-start",
            ],
        )
        assert result.returncode == 0
        data = json.loads(result.stdout.strip())
        assert data["success"] is True
        assert "worker_id" in data

    def test_strategy_optimize_missing_args(self):
        """测试优化缺少必填参数"""
        result = run_cli("strategy", ["optimize"])
        assert result.returncode != 0

    def test_strategy_optimize_invalid_json(self):
        """测试优化参数 JSON 格式错误"""
        result = run_cli(
            "strategy",
            [
                "optimize",
                "--strategy-name",
                "dual_ma",
                "--param-ranges",
                "not_valid_json",
            ],
        )
        assert result.returncode == 0
        data = json.loads(result.stdout.strip())
        assert data["success"] is False
        assert "JSON" in data["error"]

    def test_strategy_optimize_valid_json(self):
        """测试优化参数 JSON 格式正确"""
        result = run_cli(
            "strategy",
            [
                "optimize",
                "--strategy-name",
                "dual_ma",
                "--param-ranges",
                '{"fast": [5, 10], "slow": [20, 30]}',
            ],
        )
        assert result.returncode == 0
        data = json.loads(result.stdout.strip())
        assert data["success"] is True
        assert data["total_combinations"] == 4


class TestCLIData:
    """测试 data CLI 模块"""

    def test_data_help(self):
        """测试 data --help"""
        result = run_cli("data", ["--help"])
        assert result.returncode == 0
        assert "download" in result.stdout
        assert "export" in result.stdout
        assert "status" in result.stdout
        assert "list-symbols" in result.stdout
        assert "list-local-data" in result.stdout

    def test_data_list_symbols(self):
        """测试列出交易对"""
        result = run_cli("data", ["list-symbols"])
        assert result.returncode == 0

    def test_data_list_local_data(self):
        """测试列出本地数据"""
        result = run_cli("data", ["list-local-data"])
        assert result.returncode == 0

    def test_data_download_missing_args(self):
        """测试下载缺少必填参数"""
        result = run_cli("data", ["download"])
        assert result.returncode != 0


class TestCLIBacktest:
    """测试 backtest CLI 模块"""

    def test_backtest_help(self):
        """测试 backtest --help"""
        result = run_cli("backtest", ["--help"])
        assert result.returncode == 0
        assert "run" in result.stdout
        assert "list-strategies" in result.stdout

    def test_backtest_list_strategies(self):
        """测试列出回测策略"""
        result = run_cli("backtest", ["list-strategies"])
        assert result.returncode == 0


class TestCLIPlugin:
    """测试 plugin CLI 模块"""

    def test_plugin_help(self):
        """测试 plugin --help"""
        result = run_cli("plugin", ["--help"])
        assert result.returncode == 0
        assert "install" in result.stdout
        assert "list" in result.stdout
        assert "info" in result.stdout
        assert "enable" in result.stdout
        assert "disable" in result.stdout

    def test_plugin_list(self):
        """测试列出插件"""
        result = run_cli("plugin", ["list"])
        assert result.returncode == 0

    def test_plugin_info_missing_args(self):
        """测试插件详情缺少参数"""
        result = run_cli("plugin", ["info"])
        assert result.returncode != 0


class TestCLIAccount:
    """测试 account CLI 模块"""

    def test_account_help(self):
        """测试 account --help"""
        result = run_cli("account", ["--help"])
        assert result.returncode == 0
        assert "add" in result.stdout
        assert "list" in result.stdout
        assert "remove" in result.stdout

    def test_account_list(self):
        """测试列出账号"""
        result = run_cli("account", ["list"])
        assert result.returncode == 0


class TestCLIWeb:
    """测试 web CLI 模块"""

    def test_web_help(self):
        """测试 web --help"""
        result = run_cli("web", ["--help"])
        assert result.returncode == 0
        assert "search" in result.stdout
        assert "fetch" in result.stdout


class TestCLINews:
    """测试 news CLI 模块"""

    def test_news_help(self):
        """测试 news --help"""
        result = run_cli("news", ["--help"])
        assert result.returncode == 0
        assert "news" in result.stdout
        assert "sentiment" in result.stdout


class TestCLIMarket:
    """测试 market CLI 模块"""

    def test_market_help(self):
        """测试 market --help"""
        result = run_cli("market", ["--help"])
        assert result.returncode == 0
        assert "klines" in result.stdout
        assert "ticker" in result.stdout
        assert "symbols" in result.stdout
        assert "fetch" in result.stdout


class TestCLIRL:
    """测试 rl CLI 模块"""

    def test_rl_help(self):
        """测试 rl --help"""
        result = run_cli("rl", ["--help"])
        assert result.returncode == 0
        assert "train" in result.stdout
        assert "models" in result.stdout
        assert "backtest" in result.stdout
        assert "lifecycle" in result.stdout


class TestCLIAgent:
    """测试 agent CLI 模块"""

    def test_agent_help(self):
        """测试 agent --help"""
        result = run_cli("agent", ["--help"])
        assert result.returncode == 0
        assert "list" in result.stdout
        assert "send" in result.stdout
        assert "history" in result.stdout
        assert "tools" in result.stdout

    def test_agent_tools(self):
        """测试显示工具列表"""
        result = run_cli("agent", ["tools"])
        assert result.returncode == 0


class TestCLIRun:
    """测试 run CLI 模块"""

    def test_run_help(self):
        """测试 run --help"""
        result = run_cli("run", ["--help"])
        assert result.returncode == 0
        assert "--unit" in result.stdout
        assert "--integration" in result.stdout
        assert "--api" in result.stdout
        assert "--coverage" in result.stdout

    def test_run_unit_tests(self):
        """测试运行单元测试（排除有导入错误的模块）"""
        result = run_cli(
            "run",
            ["--verbose", "tests/unit/scripts/test_data_cli.py"],
            timeout=60,
        )
        # 单个测试文件应能成功执行
        assert result.returncode == 0, f"CLI run 命令失败: {result.stderr}"


class TestErrorHandling:
    """测试错误处理机制"""

    def test_invalid_module(self):
        """测试无效模块"""
        result = run_cli("nonexistent_module", ["--help"])
        assert result.returncode != 0

    def test_missing_subcommand(self):
        """测试缺少子命令"""
        # 对需要子命令的模块，仅传 --help 是可以的
        # 这里测试无效子命令
        result = run_cli("worker", ["nonexistent_command"])
        assert result.returncode != 0

    def test_invalid_argument_type(self):
        """测试无效参数类型"""
        result = run_cli("worker", ["create", "--name", "test", "--strategy-id", "invalid_id"])
        # 可能因后端未启动而失败
        assert result.returncode != 0 or "错误" in result.stdout

    def test_empty_string_argument(self):
        """测试空字符串参数 - 空名称仍可部署成功"""
        result = run_cli("strategy", ["deploy", "--strategy-name", "", "--symbols", "BTCUSDT"])
        # 空字符串被接受为有效参数，部署成功
        assert result.returncode == 0
        data = json.loads(result.stdout.strip())
        assert data["success"] is True


class TestEdgeCases:
    """测试边界情况"""

    def test_special_characters_in_name(self):
        """测试特殊字符"""
        result = run_cli(
            "strategy",
            ["deploy", "--strategy-name", "test@#$%^&*()", "--symbols", "BTCUSDT"],
        )
        # 不应崩溃
        assert result.returncode in [0, 1]

    def test_long_argument(self):
        """测试过长参数"""
        long_name = "a" * 1000
        result = run_cli(
            "strategy",
            ["deploy", "--strategy-name", long_name, "--symbols", "BTCUSDT"],
        )
        assert result.returncode in [0, 1]

    def test_unicode_arguments(self):
        """测试 Unicode 参数"""
        result = run_cli(
            "strategy",
            ["deploy", "--strategy-name", "策略_测试_🚀", "--symbols", "BTCUSDT"],
        )
        assert result.returncode in [0, 1]

    def test_multiple_instances(self):
        """测试多次执行同一命令"""
        for i in range(3):
            result = run_cli("strategy", ["list"])
            assert result.returncode == 0, f"第 {i} 次执行失败"


class TestOutputFormat:
    """测试输出格式"""

    def test_strategy_deploy_output_format(self):
        """测试部署命令输出为有效 JSON"""
        result = run_cli(
            "strategy",
            [
                "deploy",
                "--strategy-name",
                "dual_ma",
                "--symbols",
                "BTCUSDT",
            ],
        )
        assert result.returncode == 0
        output = result.stdout.strip()
        data = json.loads(output)
        assert isinstance(data, dict)
        assert "success" in data

    def test_strategy_optimize_output_format(self):
        """测试优化命令输出为有效 JSON"""
        result = run_cli(
            "strategy",
            [
                "optimize",
                "--strategy-name",
                "dual_ma",
                "--param-ranges",
                '{"param1": [1, 2]}',
            ],
        )
        assert result.returncode == 0
        output = result.stdout.strip()
        data = json.loads(output)
        assert isinstance(data, dict)
        assert "success" in data
        assert "total_combinations" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
