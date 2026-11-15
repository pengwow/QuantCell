"""外发 binance 请求的统一代理解析。

国内直连 binance REST/WS 域名不可达（2026-11-14 实测），所有外发请求必须
走代理。解析顺序与 collector 调用方保持一致：
系统配置(config.toml exchange.binance.proxy) > .env PROXY_URL > shell 环境变量。
"""

import os

from collector.config import get_binance_proxy
from config.settings import get_settings


def resolve_proxy() -> str | None:
    """返回当前生效的代理 URL；各级均未配置时返回 None（直连）。"""
    return (
        get_binance_proxy() or get_settings().proxy_url or os.environ.get("https_proxy") or os.environ.get("http_proxy")
    )
