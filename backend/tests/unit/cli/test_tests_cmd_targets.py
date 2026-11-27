"""守卫 ``cli tests`` 的筛选语义：按路径选，而不是靠可能匹配 0 个用例的 ``-m`` 标记。

历史缺陷：``--api/--auth/--schema/--error`` 曾用 ``pytest -m <mark>`` 筛选，但目标
测试文件里没有任何 pytest.mark，四个 flag 全部匹配 0 个用例并返回 exit 5。
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest

from cli import tests_cmd

BACKEND_DIR = Path(__file__).resolve().parents[3]

# 用例内部拉真实嵌套 pytest --collect-only 子进程，单跑就要 18-30s；
# xdist 邻居进程争 CPU 时全局 timeout=30 必炸，故放宽到 180s
pytestmark = pytest.mark.timeout(180)

# (flag, 构造函数, 期望目标路径)
CASES = [
    ("--integration", tests_cmd.run_integration_tests, "tests/integration"),
    ("--api", tests_cmd.run_api_tests, "tests/integration/api"),
    ("--auth", tests_cmd.run_auth_tests, "tests/integration/api/test_auth.py"),
    ("--schema", tests_cmd.run_schema_tests, "tests/integration/api/test_schema_validation.py"),
    ("--error", tests_cmd.run_error_tests, "tests/integration/api/test_error_handling.py"),
]


def _captured_target(build_cmd, monkeypatch) -> list[str]:
    """调用 CLI 构造函数并截获它要执行的命令。"""
    captured: list[list[str]] = []

    def fake_run_command(cmd, verbose=False):
        captured.append(cmd)
        return 0

    monkeypatch.setattr(tests_cmd, "run_command", fake_run_command)
    build_cmd(verbose=True)
    assert len(captured) == 1, "CLI 构造出的 pytest 命令不止一条"
    return captured[0]


@pytest.mark.parametrize(("flag", "build_cmd", "expected"), CASES, ids=[c[0] for c in CASES])
def test_flag_selects_existing_nonempty_target(flag, build_cmd, expected, monkeypatch):
    """flag → 目标路径存在且能收集到 ≥1 个用例（防止再漂移回 0 匹配）。"""
    cmd = _captured_target(build_cmd, monkeypatch)

    assert "-m" not in cmd, f"{flag} 仍在使用标记筛选: {cmd}"
    assert expected in cmd, f"{flag} 目标路径漂移: {cmd}（期望 {expected}）"
    assert (BACKEND_DIR / expected).exists(), f"{expected} 不存在"

    result = subprocess.run(
        [sys.executable, "-m", "pytest", expected, "--collect-only", "-q"],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, (
        f"{flag} 的 {expected} 收集失败 (exit {result.returncode}):\n{result.stdout[-2000:]}\n{result.stderr[-2000:]}"
    )

    match = re.search(r"(\d+) tests? collected", result.stdout)
    assert match and int(match.group(1)) >= 1, f"{flag} 的 {expected} 收集到 0 个用例:\n{result.stdout[-2000:]}"
