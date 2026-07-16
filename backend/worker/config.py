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


# axon_quant 是否可用（始终可用，因为项目已声明为依赖）
AXON_AVAILABLE = True

try:
    from axon_bridge.exchange import (
        ExchangeConfig,
        ExchangeId,
        ExchangeError,
    )
except ImportError:  # pragma: no cover - 兼容回退
    AXON_AVAILABLE = False
    ExchangeConfig = None  # type: ignore[assignment]
    ExchangeId = None  # type: ignore[assignment]
    ExchangeError = None  # type: ignore[assignment]


# =============================================================================
# 系统配置表读取工具函数
# =============================================================================

# Binance REST/WebSocket 默认 URL
_BINANCE_LIVE_REST = "https://fapi.binance.com"
_BINANCE_LIVE_WS = "wss://fstream.binance.com/ws"
_BINANCE_TESTNET_REST = "https://testnet.binance.vision"
_BINANCE_TESTNET_WS = "wss://stream.testnet.binance.vision/ws"

# OKX REST/WebSocket 默认 URL
_OKX_LIVE_REST = "https://www.okx.com"
_OKX_LIVE_WS = "wss://ws.okx.com:8443/ws/v5/private"
_OKX_TESTNET_REST = "https://www.okx.com"  # OKX 模拟盘同域名不同路径
_OKX_TESTNET_WS = "wss://wspap.okx.com:8443/ws/v5/private"


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


# =============================================================================
# 底层 axon_quant ExchangeConfig 适配（P4-live-trading 计划要求）
# =============================================================================

def build_binance_config(
    api_key: str,
    api_secret: str,
    testnet: bool = True,
    use_usdt_margin: bool = True,
    base_url_http: str | None = None,
    base_url_ws: str | None = None,
) -> Dict[str, Any]:
    """
    构建 Binance 交易所配置字典

    优先返回与 axon_quant ExchangeConfig 兼容的字典。
    当 axon_quant 不可用时，回退到最小可用配置。

    Parameters
    ----------
    api_key : str
        Binance API Key
    api_secret : str
        Binance API Secret
    testnet : bool
        是否为测试网
    use_usdt_margin : bool
        USDT 保证金开关（信息字段，存入配置供下游使用）
    base_url_http : str, optional
        自定义 REST URL
    base_url_ws : str, optional
        自定义 WebSocket URL

    Returns
    -------
    Dict[str, Any]
        交易所配置字典，包含 ``api_key``、``api_secret``、``testnet``、
        ``use_usdt_margin``、``base_url_http``、``base_url_ws`` 等字段。
    """
    if base_url_http is None:
        base_url_http = (
            _BINANCE_TESTNET_REST if testnet else _BINANCE_LIVE_REST
        )
    if base_url_ws is None:
        base_url_ws = _BINANCE_TESTNET_WS if testnet else _BINANCE_LIVE_WS

    config: Dict[str, Any] = {
        "api_key": api_key,
        "api_secret": api_secret,
        "testnet": testnet,
        "use_usdt_margin": use_usdt_margin,
        "base_url_http": base_url_http,
        "base_url_ws": base_url_ws,
        "exchange": "binance",
    }

    # 当 axon_quant 可用时，附带构造 ExchangeConfig 实例以保持兼容
    if AXON_AVAILABLE and ExchangeConfig is not None and ExchangeId is not None:
        try:
            ex_config = ExchangeConfig(
                exchange_id=ExchangeId.BINANCE,
                api_key=api_key,
                api_secret=api_secret,
                rest_base_url=base_url_http,
                ws_url=base_url_ws,
                testnet=testnet,
            )
            config["exchange_config"] = ex_config
        except Exception as e:  # pragma: no cover - 兼容容错
            logger.debug(f"构造 axon_quant ExchangeConfig 失败: {e}")

    return config


def build_binance_live_config(
    api_key: str,
    api_secret: str,
    use_usdt_margin: bool = True,
) -> Dict[str, Any]:
    """
    构建 Binance 生产环境配置便捷函数

    Parameters
    ----------
    api_key : str
        Binance API Key
    api_secret : str
        Binance API Secret
    use_usdt_margin : bool
        USDT 保证金开关

    Returns
    -------
    Dict[str, Any]
        同 :func:`build_binance_config`，``testnet=False``
    """
    return build_binance_config(
        api_key=api_key,
        api_secret=api_secret,
        testnet=False,
        use_usdt_margin=use_usdt_margin,
    )


def build_okx_config(
    api_key: str,
    api_secret: str,
    api_passphrase: str,
    testnet: bool = True,
    base_url_http: str | None = None,
    base_url_ws: str | None = None,
) -> Dict[str, Any]:
    """
    构建 OKX 交易所配置字典

    Parameters
    ----------
    api_key : str
        OKX API Key
    api_secret : str
        OKX API Secret
    api_passphrase : str
        OKX API Passphrase
    testnet : bool
        是否为模拟盘
    base_url_http : str, optional
        自定义 REST URL
    base_url_ws : str, optional
        自定义 WebSocket URL

    Returns
    -------
    Dict[str, Any]
        OKX 配置字典
    """
    if base_url_http is None:
        base_url_http = _OKX_TESTNET_REST if testnet else _OKX_LIVE_REST
    if base_url_ws is None:
        base_url_ws = _OKX_TESTNET_WS if testnet else _OKX_LIVE_WS

    config: Dict[str, Any] = {
        "api_key": api_key,
        "api_secret": api_secret,
        "api_passphrase": api_passphrase,
        "testnet": testnet,
        "base_url_http": base_url_http,
        "base_url_ws": base_url_ws,
        "exchange": "okx",
    }

    if AXON_AVAILABLE and ExchangeConfig is not None and ExchangeId is not None:
        try:
            ex_config = ExchangeConfig(
                exchange_id=ExchangeId.OKX,
                api_key=api_key,
                api_secret=api_secret,
                rest_base_url=base_url_http,
                ws_url=base_url_ws,
                testnet=testnet,
                passphrase=api_passphrase,
            )
            config["exchange_config"] = ex_config
        except Exception as e:  # pragma: no cover
            logger.debug(f"构造 OKX ExchangeConfig 失败: {e}")

    return config


def build_trading_node_config(
    exchange: str = "binance",
    account_type: str = "spot",
    trading_mode: str = "paper",
    trader_id: str = "TRADER-001",
    api_key: str | None = None,
    api_secret: str | None = None,
    api_passphrase: str | None = None,
) -> Dict[str, Any]:
    """
    构建 TradingNode 配置字典（P4-live-trading 计划 1.1-1.5 接口）

    Parameters
    ----------
    exchange : str
        交易所名称（binance/okx）
    account_type : str
        账户类型（spot/usdt_margin/coin_margin）
    trading_mode : str
        交易模式（live/testnet/paper）
    trader_id : str
        Trader ID
    api_key : str, optional
        API Key（live/testnet 模式必填）
    api_secret : str, optional
        API Secret（live/testnet 模式必填）
    api_passphrase : str, optional
        API Passphrase（仅 OKX live/testnet 模式）

    Returns
    -------
    Dict[str, Any]
        TradingNode 配置字典

    Raises
    ------
    ValueError
        不支持的交易所或交易模式
    ExchangeError
        当 axon_quant 可用且环境变量缺失时
    """
    if exchange not in ("binance", "okx"):
        raise ValueError(f"不支持的交易所: {exchange}")
    if trading_mode not in ("live", "testnet", "paper"):
        raise ValueError(f"不支持的交易模式: {trading_mode}")

    is_testnet = trading_mode == "testnet"

    if exchange == "binance":
        ex_cfg = build_binance_config(
            api_key=api_key or "",
            api_secret=api_secret or "",
            testnet=is_testnet or trading_mode == "paper",
        )
    else:
        ex_cfg = build_okx_config(
            api_key=api_key or "",
            api_secret=api_secret or "",
            api_passphrase=api_passphrase or "",
            testnet=is_testnet or trading_mode == "paper",
        )

    return {
        "trader_id": trader_id,
        "exchange": exchange,
        "account_type": account_type,
        "trading_mode": trading_mode,
        "is_testnet": is_testnet,
        "data_clients": {exchange: ex_cfg},
        "exec_clients": {exchange: ex_cfg},
        "engines": {
            "backtest_engine": True,
            "risk_engine": True,
        },
    }


__all__ = [
    "AXON_AVAILABLE",
    "get_exchange_config_from_db",
    "validate_config",
    "build_exchange_config",
    "build_binance_config",
    "build_binance_live_config",
    "build_okx_config",
    "build_trading_node_config",
]
