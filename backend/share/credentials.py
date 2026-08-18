"""
分享凭据自动生成、落盘、热重载

用于 create_share 自动配置远端凭据的工作流:
1. generate_api_key / generate_hmac_secret:生成符合远端约定的密钥
2. write_credentials_to_local_toml:合并写入 backend/config.local.toml(保留其他字段)
3. reload_remote_config:清空 ShareRemoteConfig 单例并立即重建
4. is_admin_token_configured:检查 SHARE_REMOTE_ADMIN_TOKEN 环境变量
5. ensure_remote_credentials:create_share 调远端前调用,缺失凭据则自动远端注册
"""

from __future__ import annotations

import os
import secrets
from typing import TYPE_CHECKING

import tomli
import tomli_w

from utils.logger import LogType, get_logger

from .config import CONFIG_LOCAL

if TYPE_CHECKING:
    from .config import ShareRemoteConfig


log = get_logger(__name__, LogType.APPLICATION)


class RemoteConfigError(RuntimeError):
    """远端凭据注册失败(无 admin token / 远端拒绝 / 网络异常)"""


def generate_api_key() -> str:
    """生成符合远端约定的 api_key 格式:`qck_<32 hex>`(16 字节随机)"""
    return "qck_" + secrets.token_hex(16)


def generate_hmac_secret() -> str:
    """生成符合远端约定的 hmac_secret 格式:`<64 hex>`(32 字节随机)"""
    return secrets.token_hex(32)


def write_credentials_to_local_toml(api_key: str, hmac_secret: str) -> None:
    """合并写入 config.local.toml(保留其他字段)

    仅更新 [share_remote] 段的 api_key/hmac_secret,其他段原样保留。
    enabled 字段不再写入(已废弃)。
    """
    existing: dict = {}
    if CONFIG_LOCAL.exists():
        try:
            existing = tomli.loads(CONFIG_LOCAL.read_text(encoding="utf-8"))
        except Exception as e:
            # 解析失败不应阻断流程:视为空文件继续写
            log.warning("读取 %s 失败,视为空文件: %s", CONFIG_LOCAL, e)
            existing = {}

    existing.setdefault("share_remote", {})
    existing["share_remote"]["api_key"] = api_key
    existing["share_remote"]["hmac_secret"] = hmac_secret

    CONFIG_LOCAL.write_text(tomli_w.dumps(existing), encoding="utf-8")
    log.info("share_remote 凭据已写入 %s", CONFIG_LOCAL)


def reload_remote_config() -> ShareRemoteConfig:
    """清空 ShareRemoteConfig 单例并立即重建

    运行时修改 config.local.toml 后,旧单例仍持有旧值;必须显式清空
    才能让下次访问看到新凭据。线程安全(单例内部用 _lock)。
    """
    from .config import ShareRemoteConfig

    with ShareRemoteConfig._lock:
        ShareRemoteConfig._instance = None
    return ShareRemoteConfig()  # 立即重建,触发新一次 _init()


def is_admin_token_configured() -> bool:
    """是否配置了远端 admin token(用于前端判断降级路径)

    环境变量名:SHARE_REMOTE_ADMIN_TOKEN
    """
    return bool(os.getenv("SHARE_REMOTE_ADMIN_TOKEN"))


def ensure_remote_credentials(
    name: str = "QuantCell-PC",
    user_id: str = "anonymous",
) -> tuple[str, str]:
    """确保 ShareRemoteConfig 凭据已就绪;否则尝试远端 auto-register。

    行为:
    - cfg.is_ready=True  → 直接返回 (api_key, hmac_secret),不做任何 IO
    - cfg.is_ready=False → 读取 SHARE_REMOTE_ADMIN_TOKEN
      - 无值 → 抛 RemoteConfigError
      - 有值 → 调远端 register_device_sync,写入 config.local.toml,reload,
              返回新凭据

    Args:
        name: 设备显示名(传给远端)
        user_id: 用户标识(传给远端)

    Returns:
        (api_key, hmac_secret)

    Raises:
        RemoteConfigError: 凭据缺失且无法通过远端自动配置
    """
    from .config import get_remote_config
    from .remote_client import RemoteShareClient, RemoteShareError

    cfg = get_remote_config()
    if cfg.is_ready:
        return cfg.api_key, cfg.hmac_secret  # type: ignore[return-value]

    admin_token = os.getenv("SHARE_REMOTE_ADMIN_TOKEN")
    if not admin_token:
        log.error("远端凭据未配置且 SHARE_REMOTE_ADMIN_TOKEN 未设置:无法自动注册")
        msg = "缺少 SHARE_REMOTE_ADMIN_TOKEN,无法自动注册远端凭据。请联系管理员配置后重启服务。"
        raise RemoteConfigError(msg)

    try:
        client = RemoteShareClient(cfg)
        result = client.register_device_sync(admin_token=admin_token, name=name, user_id=user_id)
    except RemoteShareError as e:
        log.error("远端 auto-register 失败: %s", e)
        msg = f"远端凭据注册失败: {e}"
        raise RemoteConfigError(msg) from e

    api_key = result["api_key"]
    hmac_secret = result["hmac_secret"]
    write_credentials_to_local_toml(api_key, hmac_secret)
    reload_remote_config()
    log.info("远端凭据已自动注册并写入 config.local.toml")
    return api_key, hmac_secret
