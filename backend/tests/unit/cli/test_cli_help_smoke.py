"""CLI 全量 --help 门禁：16 个子命令都必须可用且有 Usage 输出。"""

import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cli import app, register_commands

register_commands()

BACKEND_DIR = Path(__file__).resolve().parents[3]

SUBCOMMANDS = [
    "agent",
    "factor",
    "market",
    "news",
    "plugin",
    "research",
    "rl",
    "web",
    "worker",
    "tests",
    "account",
    "migrate",
    "strategy",
    "backtest",
    "jobs",
    "data",
]


@pytest.fixture
def runner():
    return CliRunner()


@pytest.mark.parametrize("name", SUBCOMMANDS)
def test_subcommand_help(runner, name):
    """每个子命令 --help 必须 exit 0 且输出 Usage。"""
    result = runner.invoke(app, [name, "--help"])
    assert result.exit_code == 0, f"quantcell {name} --help 失败: {result.output}"
    assert "Usage" in result.output, f"quantcell {name} --help 未输出 Usage"


def test_migrate_module_direct_run_help():
    """python -m cli.migrate --help 必须可用（API 路由引导用户直跑该路径）。"""
    result = subprocess.run(
        [sys.executable, "-m", "cli.migrate", "--help"],
        cwd=str(BACKEND_DIR),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, f"直跑失败: {result.stderr}"
    assert "Usage" in result.stdout, f"直跑无输出: stdout={result.stdout!r}"
