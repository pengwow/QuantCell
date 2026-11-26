"""桌面端可选扩展静态清单与安装目录工具。

扩展 = 体积大、非主链路必需的一组 Python 依赖。安装参数只来自 EXTENSIONS
白名单，REST 层不接受客户端传入的包名（防注入）。
"""

from __future__ import annotations

import json
import platform
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

# PyPI 查询超时（秒）：失败静默回退静态 approx_size_mb，不阻塞列表接口
_PYPI_TIMEOUT = 5.0
_PYPI_URL = "https://pypi.org/pypi/{name}/json"
_MIB = 1024 * 1024


@dataclass(frozen=True)
class ExtensionSpec:
    id: str
    name: str
    category: str
    description: str
    deps: tuple[str, ...]
    approx_size_mb: int
    purpose: str


EXTENSIONS: tuple[ExtensionSpec, ...] = (
    ExtensionSpec(
        id="rl",
        name="AI 训练依赖（RL 强化学习）",
        category="ai-training",
        description="stable-baselines3 + gymnasium + torch，用于策略训练与 RL 回测",
        deps=("torch", "stable-baselines3", "gymnasium"),
        approx_size_mb=600,
        purpose="启用策略页和任务中的 RL 训练/推理（未安装时显示降级提示）",
    ),
)


def get_extension(ext_id: str) -> ExtensionSpec | None:
    """按 id 查扩展，未知 id 返回 None（路由层据此回 404）。"""
    return next((e for e in EXTENSIONS if e.id == ext_id), None)


def extensions_root(data_dir: str | Path) -> Path:
    return Path(data_dir) / "extensions"


def site_packages_dir(data_dir: str | Path, ext_id: str) -> Path:
    return extensions_root(data_dir) / ext_id / "site-packages"


def is_installed(data_dir: str | Path, ext_id: str) -> bool:
    """site-packages 存在且非空即视为已装（卸载幂等删除整个扩展目录）。"""
    sp = site_packages_dir(data_dir, ext_id)
    return sp.is_dir() and any(sp.iterdir())


def installed_versions(data_dir: str | Path, ext_id: str) -> dict[str, str]:
    """扫描 *.dist-info 目录名得到 {归一化包名: 版本}，未装返回 {}。"""
    sp = site_packages_dir(data_dir, ext_id)
    if not sp.is_dir():
        return {}
    versions: dict[str, str] = {}
    for child in sp.glob("*.dist-info"):
        if not child.is_dir():
            continue
        name, sep, version = child.name[: -len(".dist-info")].rpartition("-")
        if sep:
            # PEP 503：包名比较时下划线归一为连字符、忽略大小写
            versions[name.replace("_", "-").lower()] = version
    return versions


def _pypi_json(pkg: str, timeout: float = _PYPI_TIMEOUT) -> dict:
    """请求 PyPI JSON API；单独成函数便于单测 monkeypatch（不打真实网络）。"""
    with urllib.request.urlopen(_PYPI_URL.format(name=pkg), timeout=timeout) as resp:
        return json.load(resp)


def _wheel_matches_current_platform(filename: str) -> bool:
    """判断 wheel 文件名的 platform tag 是否匹配当前机器。

    ponytail: 只做 mac/win/linux × arm64/x86_64 的粗匹配，不实现完整 PEP 425
    tag 集合运算；升级路径是改用 packaging.tags.sys_tags() 精确匹配。
    """
    name = filename.lower()
    if not name.endswith(".whl"):
        return False
    plat_tag = name[:-4].rsplit("-", 1)[-1]
    if plat_tag == "any":  # 纯 Python wheel 全平台通用
        return True
    machine = platform.machine().lower()
    if sys.platform == "darwin":
        arch = "arm64" if machine == "arm64" else "x86_64"
        return "macosx" in plat_tag and arch in plat_tag
    if sys.platform == "win32":
        return "win_arm64" in plat_tag if machine in ("arm64", "aarch64") else "win_amd64" in plat_tag
    arch = "aarch64" if machine in ("arm64", "aarch64") else "x86_64"
    return ("manylinux" in plat_tag or "musllinux" in plat_tag) and arch in plat_tag


def _pick_download_size(urls: list[dict]) -> int | None:
    """选当前平台 wheel 的字节数；无匹配退化为最大 wheel，再退化为 sdist。"""
    wheels = [u for u in urls if u.get("packagetype") == "bdist_wheel"]
    matched = [u for u in wheels if _wheel_matches_current_platform(u["filename"])]
    candidates = matched or wheels
    if not candidates:
        candidates = [u for u in urls if u.get("packagetype") == "sdist"]
    if not candidates:
        return None
    return max(u["size"] for u in candidates)


def live_total_size_mb(deps: tuple[str, ...]) -> int | None:
    """估算当前平台各直接依赖下载量之和（MB，四舍五入）；任一查询失败返回 None。

    只统计 manifest 中直接列出的包，不含传递依赖，属偏保守的近似展示值。
    """
    total = 0
    for pkg in deps:
        try:
            data = _pypi_json(pkg)
        except OSError, ValueError:
            return None
        size = _pick_download_size(data.get("urls", []))
        if size is None:
            return None
        total += size
    return round(total / _MIB)
