"""installer 单测：fake uv 脚本锁定命令参数、进度解析、失败清理、并发防重、卸载。"""

from __future__ import annotations

import os
import stat
import sys
import time
from pathlib import Path

import pytest

from extensions import installer
from extensions.manifest import get_extension

# fake uv 是 POSIX bash 脚本；Windows 本机执行用例跳过（CI 后端测试在 Linux）
pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="fake uv 为 POSIX shell 脚本")


@pytest.fixture(autouse=True)
def _reset_tasks():
    installer._reset()
    yield
    installer._reset()


@pytest.fixture
def fake_uv(tmp_path: Path) -> Path:
    """记录 argv 到日志、输出预制进度行，行为由 FAKE_UV_FAIL / FAKE_UV_SLEEP 环境变量驱动。

    argv 位置：$1=pip $2=install $3=--target $4=<target 目录>
    """
    log = tmp_path / "argv.log"
    script = tmp_path / "uv"
    script.write_text(
        """#!/usr/bin/env bash
set -eu
echo "$@" >> "$FAKE_UV_LOG"
echo "Resolved 3 packages in 1ms"
if [[ "${FAKE_UV_FAIL:-0}" == "1" ]]; then
  mkdir -p "$4"
  echo "half-baked" > "$4/.partial"
  echo "error: network disconnected"
  exit 2
fi
echo "Downloading 3 packages (12.0 MiB)"
printf 'Downloading [==] 6.0 MiB/12.0 MiB\\r'
printf 'Downloading [====] 12.0 MiB/12.0 MiB\\r'
echo "Installed 3 packages in 2s"
mkdir -p "$4"
echo "ok" > "$4/INSTALLED"
sleep "${FAKE_UV_SLEEP:-0}"
"""
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    os.environ["FAKE_UV_LOG"] = str(log)
    return script


def _wait_terminal(task_id: str, timeout: float = 5.0) -> installer.TaskState:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = installer.get_task(task_id)
        if state and state.status in ("done", "error"):
            return state
        time.sleep(0.01)
    raise AssertionError("安装任务未在超时内结束")


def test_install_success_locks_argv(tmp_path: Path, fake_uv: Path):
    rl = get_extension("rl")
    task_id = installer.start_install(rl, str(tmp_path), str(fake_uv))
    state = _wait_terminal(task_id)
    assert state.status == "done"
    assert state.pct == 100

    argv = Path(tmp_path / "argv.log").read_text().strip().splitlines()[0].split()
    assert argv[:2] == ["pip", "install"]
    target = argv[argv.index("--target") + 1]
    assert target == str(tmp_path / "extensions" / "rl" / "site-packages")
    assert argv[argv.index("--python-platform") + 1] == installer.uv_python_platform()
    assert argv[argv.index("--python-version") + 1] == "3.14"
    for dep in rl.deps:  # 包名只能来自 manifest 白名单
        assert dep in argv
    assert (tmp_path / "extensions" / "rl" / "site-packages" / "INSTALLED").exists()
    assert installer.running_task_id("rl") is None
    assert installer.last_task_id("rl") == task_id  # 终态保留供轮询


def test_install_failure_cleans_half_product(tmp_path: Path, fake_uv: Path, monkeypatch):
    monkeypatch.setenv("FAKE_UV_FAIL", "1")
    task_id = installer.start_install(get_extension("rl"), str(tmp_path), str(fake_uv))
    state = _wait_terminal(task_id)
    assert state.status == "error"
    assert "退出码 2" in state.detail
    assert not (tmp_path / "extensions" / "rl").exists()  # 半成品目录已清
    assert installer.running_task_id("rl") is None


def test_concurrent_install_rejected(tmp_path: Path, fake_uv: Path, monkeypatch):
    monkeypatch.setenv("FAKE_UV_SLEEP", "1")
    task_id = installer.start_install(get_extension("rl"), str(tmp_path), str(fake_uv))
    try:
        with pytest.raises(installer.InstallRunningError):
            installer.start_install(get_extension("rl"), str(tmp_path), str(fake_uv))
        assert installer.running_task_id("rl") == task_id
    finally:
        _wait_terminal(task_id)


def test_uninstall_idempotent(tmp_path: Path):
    installer.uninstall(str(tmp_path), "rl")  # 不存在也不抛
    target = tmp_path / "extensions" / "rl" / "site-packages"
    target.mkdir(parents=True)
    (target / "x").write_text("x")
    installer.uninstall(str(tmp_path), "rl")
    assert not (tmp_path / "extensions" / "rl").exists()
    installer.uninstall(str(tmp_path), "rl")  # 二次删除不抛


def test_parse_line_progress_state_machine():
    s = installer.TaskState(status="resolving", pct=0)
    installer._parse_line(s, "Resolved 3 packages in 1ms")
    assert s.status == "downloading" and s.pct == 5
    installer._parse_line(s, "Downloading [==] 6.0 MiB/12.0 MiB")
    assert s.pct == 47  # 5 + 85 × (6/12) = 47
    installer._parse_line(s, "\rDownloading [====] 12.0 MiB/12.0 MiB")
    assert s.pct == 90
    installer._parse_line(s, "Installed 3 packages in 2s")
    assert s.status == "installing" and s.pct == 95


@pytest.mark.parametrize(
    "plat,machine,expected",
    [
        ("darwin", "arm64", "aarch64-apple-darwin"),
        ("darwin", "x86_64", "x86_64-apple-darwin"),
        ("win32", "AMD64", "x86_64-pc-windows-msvc"),
        ("win32", "ARM64", "aarch64-pc-windows-msvc"),
        ("linux", "x86_64", "x86_64-unknown-linux-gnu"),
        ("linux", "aarch64", "aarch64-unknown-linux-gnu"),
    ],
)
def test_uv_python_platform_mapping(monkeypatch, plat, machine, expected):
    monkeypatch.setattr(sys, "platform", plat)
    monkeypatch.setattr(installer.platform, "machine", lambda: machine)
    assert installer.uv_python_platform() == expected
