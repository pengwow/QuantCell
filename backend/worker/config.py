# -*- coding: utf-8 -*-
"""
Worker 配置模块

提供交易所配置和验证功能。
使用 axon_quant 作为底层交易引擎。

使用示例：
    from worker.config import validate_config, get_exchange_config_from_db
"""

from __future__ import annotations

import os
from typing import Any, Dict, Literal, Tuple

from utils.logger import get_logger, LogType

logger = get_logger(__name__, LogType.SYSTEM)


# =============================================================================
# 系统配置表读取工具函数
# =============================================================================

def get_exchange_config_from_db(
    exchange: str,
    trading_mode: str,
) -> tuple[str | None, str | None]:
    """
    从系统配置表读取交易所 API 密钥

    Parameters
    ----------
    exchange : str
        交易所名称（binance/okx）
    trading_mode : str
        交易模式（live/testnet/paper）

    Returns
    -------
    tuple[str | None, str | None]
        (api_key, api_secret)，如果未找到则返回 (None, None)
    """
    try:
        from settings.models import SystemConfigBusiness

        prefix = f"exchange.{exchange}"
        is_testnet = trading_mode == "testnet"

        if is_testnet:
            key_key = f"{prefix}.testnet_api_key"
            secret_key = f"{prefix}.testnet_api_secret"
        else:
            key_key = f"{prefix}.live_api_key"
            secret_key = f"{prefix}.live_api_secret"

        api_key = SystemConfigBusiness.get(key_key)
        api_secret = SystemConfigBusiness.get(secret_key)

        if api_key and api_secret:
            logger.info(f"从系统配置表成功读取 {exchange} API 配置（模式: {trading_mode}）")
            return api_key, api_secret

        logger.warning(f"系统配置表中未找到 {exchange} API 配置（模式: {trading_mode}），尝试回退到环境变量")
        return None, None

    except Exception as e:
        logger.warning(f"从系统配置表读取 {exchange} 配置失败: {e}，回退到环境变量")
        return None, None


def validate_config(
    exchange: str,
    trading_mode: str,
    api_key: str | None,
    api_secret: str | None,
    api_passphrase: str | None = None,
) -> Tuple[bool, str]:
    """
    验证配置是否有效

    Parameters
    ----------
    exchange : str
        交易所
    trading_mode : str
        交易模式
    api_key : str | None
        API Key
    api_secret : str | None
        API Secret
    api_passphrase : str | None
        API Passphrase（仅OKX）

    Returns
    -------
    Tuple[bool, str]
        (是否有效, 错误信息)
    """
    if exchange not in ["binance", "okx"]:
        return False, f"不支持的交易所: {exchange}"

    if trading_mode not in ["live", "testnet", "paper"]:
        return False, f"不支持的交易模式: {trading_mode}"

    if trading_mode != "paper":
        if not api_key:
            return False, "API Key 不能为空"
        if not api_secret:
            return False, "API Secret 不能为空"
        if exchange == "okx" and not api_passphrase:
            return False, "OKX 需要 API Passphrase"

    return True, ""


def build_exchange_config(
    exchange: str,
    trading_mode: str,
) -> Dict[str, Any]:
    """
    构建交易所配置字典

    Parameters
    ----------
    exchange : str
        交易所名称（binance/okx）
    trading_mode : str
        交易模式（live/testnet/paper）

    Returns
    -------
    Dict[str, Any]
        交易所配置字典
    """
    api_key = None
    api_secret = None

    if trading_mode != "paper":
        api_key, api_secret = get_exchange_config_from_db(exchange, trading_mode)

        if api_key is None:
            env_prefix = exchange.upper()
            if trading_mode == "testnet":
                api_key = os.environ.get(f"{env_prefix}_TESTNET_API_KEY")
                api_secret = os.environ.get(f"{env_prefix}_TESTNET_API_SECRET")
            else:
                api_key = os.environ.get(f"{env_prefix}_API_KEY")
                api_secret = os.environ.get(f"{env_prefix}_API_SECRET")

    return {
        "exchange": exchange,
        "trading_mode": trading_mode,
        "api_key": api_key,
        "api_secret": api_secret,
    }


__all__ = [
    "get_exchange_config_from_db",
    "validate_config",
    "build_exchange_config",
]
