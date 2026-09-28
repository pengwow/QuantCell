"""扩展安装执行器：后台线程调用随包 uv 二进制安装到数据目录。

- 安装参数只来自 manifest 白名单；目标路径恒为 <data>/extensions/<id>/site-packages
- 进度保存在进程内字典（sidecar 重启即清空；终态额外保留在 _last_task）
- 同一扩展并发安装被拒（InstallRunningError → 路由层 409）
- 安装失败清理半成品扩展目录，避免下次 uv --target 合并脏状态
"""

from __future__ import annotations

import platform
import re
import shutil
import subprocess
import sys
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path

from extensions.manifest import (
    ExtensionSpec,
    extensions_root,
    is_installed,
    site_packages_dir,
)
from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)

# sidecar 冻结运行时基于 Python 3.14（backend/pyproject.toml requires-python >=3.14）
_TARGET_PYTHON_VERSION = "3.14"

# uv 输出单位 → MiB
_UNIT_MIB = {
    "KIB": 1 / 1024,
    "KB": 1 / 1024,
    "MIB": 1.0,
    "MB": 1.0,
    "GIB": 1024.0,
    "GB": 1024.0,
}
# 例：Downloading 27 packages (42.3 MiB)
_TOTAL_RE = re.compile(r"Downloading\s+\d+\s+packages?\s*\(\s*([\d.]+)\s*(KiB|MiB|GiB|KB|MB|GB)")
# 例：Downloading [████░░] 8.4 MiB/300.2 MiB（进度条用 \r 刷新，可能在同一行内）
_PROGRESS_RE = re.compile(r"([\d.]+)\s*(KiB|MiB|GiB|KB|MB|GB)\s*/\s*([\d.]+)\s*(KiB|MiB|GiB|KB|MB|GB)")


class InstallRunningError(RuntimeError):
    """同一扩展已有安装任务在跑（路由层映射 409）。"""


@dataclass
class TaskState:
    status: str  # resolving | downloading | installing | done | error
    pct: int
    detail: str = ""
    total_mib: float = 0.0  # 由 "Downloading N packages (X MiB)" 行捕获


_tasks: dict[str, TaskState] = {}
_running: dict[str, str] = {}  # ext_id -> 活动 task_id
_last_task: dict[str, str] = {}  # ext_id -> 最近一次 task_id（含终态）
_lock = threading.Lock()


def _reset() -> None:
    """清空任务表（仅供测试隔离使用）。"""
    with _lock:
        _tasks.clear()
        _running.clear()
        _last_task.clear()


def get_task(task_id: str) -> TaskState | None:
    return _tasks.get(task_id)


def running_task_id(ext_id: str) -> str | None:
    return _running.get(ext_id)


def last_task_id(ext_id: str) -> str | None:
    return _last_task.get(ext_id)


def uv_python_platform() -> str:
    """当前机器 → uv --python-platform 完整 triple。

    sys.platform 的 darwin/win32 不是 uv 合法值（uv 只认 windows/linux/macos
    简写或完整 triple）；输出 triple 与 CI 打包矩阵一一对应。Linux 桌面只支持
    gnu（ubuntu），musl 不在支持矩阵。
    """
    machine = platform.machine().lower()
    if sys.platform == "darwin":
        return "aarch64-apple-darwin" if machine == "arm64" else "x86_64-apple-darwin"
    if sys.platform == "win32":
        if machine in ("arm64", "aarch64"):
            return "aarch64-pc-windows-msvc"
        return "x86_64-pc-windows-msvc"
    if machine in ("arm64", "aarch64"):
        return "aarch64-unknown-linux-gnu"
    return "x86_64-unknown-linux-gnu"


def _build_cmd(uv_bin: str, target: Path, deps: tuple[str, ...]) -> list[str]:
    """组装 uv 命令；包名只来自 deps（manifest 白名单），无任何客户端输入。"""
    return [
        uv_bin,
        "pip",
        "install",
        "--target",
        str(target),
        "--python-platform",
        uv_python_platform(),
        "--python-version",
        _TARGET_PYTHON_VERSION,
        *deps,
    ]


def _parse_line(state: TaskState, raw_line: str) -> None:
    """按行（含 \\r 刷新片段）更新状态机与进度百分比。"""
    line = raw_line.strip()
    if not line:
        return
    if line.startswith("Resolved"):
        state.status = "downloading"
        state.pct = max(state.pct, 5)
        state.detail = "依赖解析完成，开始下载"
        return
    total_match = _TOTAL_RE.search(line)
    if total_match:
        state.total_mib = max(
            state.total_mib,
            float(total_match.group(1)) * _UNIT_MIB[total_match.group(2).upper()],
        )
        state.status = "downloading"
        return
    prog_match = _PROGRESS_RE.search(line)
    if prog_match and state.status in ("resolving", "downloading"):
        done = float(prog_match.group(1)) * _UNIT_MIB[prog_match.group(2).upper()]
        total = float(prog_match.group(3)) * _UNIT_MIB[prog_match.group(4).upper()]
        state.total_mib = max(state.total_mib, total)
        state.status = "downloading"
        if state.total_mib > 0:
            state.pct = max(state.pct, min(90, int(5 + 85 * done / state.total_mib)))
        state.detail = f"下载中 {done:.1f}/{state.total_mib:.1f} MiB"
        return
    if line.startswith("Installed"):
        state.status = "installing"
        state.pct = 95
        state.detail = "正在写入安装目录"
        return
    # 其余行（Preparing/Downloading <pkg>...）作为 detail 透传，保留最后一条
    if state.status in ("resolving", "downloading"):
        state.detail = line[:200]


def start_install(spec: ExtensionSpec, data_dir: str, uv_bin: str) -> str:
    """注册并启动后台安装任务，返回 task_id；同扩展重复启动抛 InstallRunningError。"""
    with _lock:
        if spec.id in _running:
            raise InstallRunningError(f"扩展 {spec.id} 正在安装中")
        task_id = uuid.uuid4().hex
        _tasks[task_id] = TaskState(status="resolving", pct=0, detail="准备安装环境")
        _running[spec.id] = task_id
        _last_task[spec.id] = task_id

    threading.Thread(
        target=_run_install,
        args=(task_id, spec, data_dir, uv_bin),
        daemon=True,
    ).start()
    return task_id


def _run_install(task_id: str, spec: ExtensionSpec, data_dir: str, uv_bin: str) -> None:
    state = _tasks[task_id]
    ext_dir = extensions_root(data_dir) / spec.id
    target = site_packages_dir(data_dir, spec.id)
    ok = False
    detail = ""
    try:
        # 重试场景：先清掉上次失败残留，uv --target 不负责清理半成品
        if ext_dir.exists():
            shutil.rmtree(ext_dir)
        target.mkdir(parents=True, exist_ok=True)

        proc = subprocess.Popen(
            _build_cmd(uv_bin, target, spec.deps),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # uv 错误信息也走同一进度通道
            text=True,
            bufsize=1,
        )
        assert proc.stdout is not None
        for chunk in proc.stdout:
            # splitlines 同时按 \r / \n / \r\n 切分，正确处理进度条刷新
            for segment in chunk.splitlines():
                _parse_line(state, segment)
        code = proc.wait()
        if code != 0:
            raise RuntimeError(f"uv 退出码 {code}")
        if not is_installed(data_dir, spec.id):
            raise RuntimeError("安装结束但目标目录为空")
        ok = True
        detail = "安装完成"
        logger.info(f"扩展 {spec.id} 安装完成: {target}")
    except Exception as exc:
        detail = str(exc)[:200]
        logger.error(f"扩展 {spec.id} 安装失败: {exc}")
        shutil.rmtree(ext_dir, ignore_errors=True)
    finally:
        # 终态（done/error）必须在半成品清理与 _running 注销完成后再发布：
        # 轮询方一旦读到终态，就要能保证目录已清、并发锁已释放（可立即卸载/重装）。
        with _lock:
            _running.pop(spec.id, None)
            if ok:
                state.status = "done"
                state.pct = 100
            else:
                state.status = "error"
            state.detail = detail


def uninstall(data_dir: str, ext_id: str) -> None:
    """幂等删除扩展整个目录。"""
    shutil.rmtree(extensions_root(data_dir) / ext_id, ignore_errors=True)
