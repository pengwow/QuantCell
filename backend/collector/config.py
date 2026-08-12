"""采集器配置工具。

集中管理采集器相关配置的读取与默认值，避免在业务代码里散落
`os.path.join` / `Path("...")` 等硬编码。

约定:
- 所有配置项都从 system_config (settings SystemConfigBusiness) 读取
- 读取失败 / 未配置时, 退回默认值
- 默认 base_dir 走 backend/data/source/archive
"""
from __future__ import annotations

import os
from pathlib import Path

from utils.logger import get_logger, LogType

logger = get_logger(__name__, LogType.APPLICATION)


def _default_archive_base_dir() -> Path:
    """归档数据默认根目录: backend/data/source/archive."""
    return Path(__file__).resolve().parent.parent / "data" / "source" / "archive"


def _read_config(key: str, default: str) -> str:
    """从 system_config 读字符串配置, 失败退回 default."""
    try:
        from settings.models import SystemConfigBusiness
        value = SystemConfigBusiness.get(key, default)
        if value is None or value == "":
            return default
        return str(value)
    except Exception as exc:  # 数据库未就绪等情况
        logger.debug(f"读取配置 {key} 失败, 使用默认 {default}: {exc}")
        return default


def get_archive_base_dir() -> Path:
    """获取归档数据存储根目录。

    优先从 system_config `data.archive.base_dir` 读取, 失败时
    退回 backend/data/source/archive。
    """
    raw = _read_config("data.archive.base_dir", str(_default_archive_base_dir()))
    p = Path(raw)
    if not p.is_absolute():
        # 相对路径相对 backend 根目录解析
        backend_root = Path(__file__).resolve().parent.parent
        p = backend_root / raw
    return p


def get_binance_proxy() -> str | None:
    """获取 Binance 代理地址 (HTTP 代理 URL), 未配置时返回 None."""
    raw = _read_config("exchange.binance.proxy", "")
    return raw or None


__all__ = [
    "get_archive_base_dir",
    "get_binance_proxy",
]
