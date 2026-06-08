# -*- coding: utf-8 -*-
"""
分享系统 远端集成配置

集中读取 quantcell.top 远端分发服务的端点与凭据。

加载顺序（优先级从高到低）：
1. 环境变量 SHARE_REMOTE_*           —— 便于容器/部署覆盖
2. backend/config.local.toml         —— 本地敏感信息（.gitignore）
3. backend/config.toml               —— 仓库内默认配置（仅占位）

未配置 api_key / hmac_secret 时，RemoteShareClient 进入"禁用远端"模式，
回退到本地分享（仅本机可见），避免误用导致空指针或裸调。
"""
from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Optional

import tomli

from utils.logger import get_logger, LogType

logger = get_logger(__name__, LogType.APPLICATION)


_BACKEND_ROOT = Path(__file__).resolve().parent.parent


def _load_toml_chain() -> dict:
    """依次读取 config.toml → config.local.toml，后者覆盖前者"""
    merged: dict = {}
    for name in ("config.toml", "config.local.toml"):
        path = _BACKEND_ROOT / name
        if not path.exists():
            continue
        try:
            with open(path, "rb") as f:
                merged.update(tomli.load(f) or {})
        except Exception as e:
            logger.warning("读取 %s 失败: %s", path, e)
    return merged


class ShareRemoteConfig:
    """分享远端（quantcell.top）配置（线程安全单例）"""

    _instance: Optional["ShareRemoteConfig"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "ShareRemoteConfig":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init()
        return cls._instance

    def _init(self) -> None:
        cfg = _load_toml_chain()
        remote = cfg.get("share_remote", {}) or {}

        # 基础端点（可被环境变量覆盖）
        self.base_url: str = (
            os.getenv("SHARE_REMOTE_BASE_URL")
            or remote.get("base_url")
            or "https://share.quantcell.top"
        ).rstrip("/")

        self.timeout_seconds: float = float(
            os.getenv("SHARE_REMOTE_TIMEOUT")
            or remote.get("timeout_seconds", 10)
        )

        # 凭据：必须显式配置；未配置则视为远端未启用
        self.api_key: Optional[str] = (
            os.getenv("SHARE_REMOTE_API_KEY") or remote.get("api_key")
        )
        self.hmac_secret: Optional[str] = (
            os.getenv("SHARE_REMOTE_HMAC_SECRET") or remote.get("hmac_secret")
        )

        # 总开关（默认关闭以便双写灰度）
        enabled_env = os.getenv("SHARE_REMOTE_ENABLED")
        if enabled_env is not None:
            self.enabled: bool = enabled_env.lower() in ("1", "true", "yes", "on")
        else:
            self.enabled = bool(remote.get("enabled", False))

        # 重试策略
        self.max_retries: int = int(remote.get("max_retries", 3))
        self.retry_backoff: float = float(remote.get("retry_backoff", 0.6))

    @property
    def is_ready(self) -> bool:
        """是否所有远端依赖都就绪（用于判断能否发起真实上传）"""
        return (
            self.enabled
            and bool(self.api_key)
            and bool(self.hmac_secret)
        )

    def summary(self) -> dict:
        """用于日志/调试的脱敏摘要（不打印任何 secret）"""
        return {
            "base_url": self.base_url,
            "enabled": self.enabled,
            "ready": self.is_ready,
            "has_api_key": bool(self.api_key),
            "has_hmac_secret": bool(self.hmac_secret),
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
        }


def get_remote_config() -> ShareRemoteConfig:
    """获取分享远端配置单例"""
    return ShareRemoteConfig()
