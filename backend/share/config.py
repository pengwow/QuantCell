"""
分享系统 远端集成配置

集中读取 quantcell.top 远端分发服务的端点与凭据。

加载顺序（优先级从高到低）：
1. 环境变量 SHARE_REMOTE_*           —— 便于容器/部署覆盖
2. backend/config.local.toml         —— 本地敏感信息（.gitignore）
3. backend/config.toml               —— 仓库内默认配置（仅占位）

未配置 api_key / hmac_secret 时,create_share 在调远端前会先
调用 ensure_remote_credentials()(调远端 auto-register 拿凭据,
写到 backend/config.local.toml)。
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

import tomli

from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)


_BACKEND_ROOT = Path(__file__).resolve().parent.parent

# 集中维护 toml 路径,被 credentials.py 与本模块的 _load_toml_chain 共用
CONFIG_LOCAL = _BACKEND_ROOT / "config.local.toml"
CONFIG_DEFAULT = _BACKEND_ROOT / "config.toml"


def _load_toml_chain() -> dict:
    """依次读取 config.toml → config.local.toml,后者覆盖前者

    路径统一来自模块顶部常量,便于测试时整体 monkeypatch。
    """
    merged: dict = {}
    for path in (CONFIG_DEFAULT, CONFIG_LOCAL):
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

    _instance: ShareRemoteConfig | None = None
    _lock = threading.Lock()

    def __new__(cls) -> ShareRemoteConfig:
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
            os.getenv("SHARE_REMOTE_BASE_URL") or remote.get("base_url") or "https://share.quantcell.top"
        ).rstrip("/")

        self.timeout_seconds: float = float(os.getenv("SHARE_REMOTE_TIMEOUT") or remote.get("timeout_seconds", 10))

        # 凭据：必须显式配置；未配置则视为远端未启用
        self.api_key: str | None = os.getenv("SHARE_REMOTE_API_KEY") or remote.get("api_key")
        self.hmac_secret: str | None = os.getenv("SHARE_REMOTE_HMAC_SECRET") or remote.get("hmac_secret")

        # 重试策略
        self.max_retries: int = int(remote.get("max_retries", 3))
        self.retry_backoff: float = float(remote.get("retry_backoff", 0.6))

    @property
    def is_ready(self) -> bool:
        """是否所有远端依赖都就绪(api_key + hmac_secret 都已配置)"""
        return bool(self.api_key) and bool(self.hmac_secret)

    @classmethod
    def reload(cls) -> ShareRemoteConfig:
        """清空单例并重建(写完 config.local.toml 后调用)

        运行时修改 toml 后,旧单例仍持有旧值;必须显式清空才能让下次访问
        看到新凭据。线程安全(类内 _lock 保护)。
        """
        with cls._lock:
            cls._instance = None
        return cls()  # 立即重建,触发新一次 _init()

    def summary(self) -> dict:
        """用于日志/调试的脱敏摘要（不打印任何 secret）"""
        return {
            "base_url": self.base_url,
            "ready": self.is_ready,
            "has_api_key": bool(self.api_key),
            "has_hmac_secret": bool(self.hmac_secret),
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
        }


def get_remote_config() -> ShareRemoteConfig:
    """获取分享远端配置单例"""
    return ShareRemoteConfig()
