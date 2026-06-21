# -*- coding: utf-8 -*-
"""axon 交易所配置

替代原 worker/config.py 中的 nautilus TradingNodeConfig。
使用简化的配置字典，不依赖 nautilus_trader。
"""
from __future__ import annotations

import os
from typing import Any, Dict


def build_exchange_config(exchange: str, trading_mode: str = "testnet") -> Dict[str, Any]:
    """构建交易所配置。

    Args:
        exchange: 交易所名称（binance/okx）。
        trading_mode: 交易模式（testnet/production）。

    Returns:
        配置字典。

    Raises:
        ValueError: 不支持的交易所或缺少环境变量。
    """
    exchange = exchange.lower()

    if exchange == "binance":
        return _build_binance_config(trading_mode)
    elif exchange == "okx":
        return _build_okx_config(trading_mode)
    else:
        raise ValueError(f"不支持的交易所: {exchange}，目前支持 binance/okx")


def _build_binance_config(trading_mode: str) -> Dict[str, Any]:
    api_key = os.environ.get("BINANCE_API_KEY", "")
    api_secret = os.environ.get("BINANCE_API_SECRET", "")

    if not api_key or not api_secret:
        raise ValueError(
            "缺少 Binance API 密钥，请设置 BINANCE_API_KEY 和 BINANCE_API_SECRET 环境变量"
        )

    is_testnet = trading_mode == "testnet"
    return {
        "exchange": "binance",
        "api_key": api_key,
        "api_secret": api_secret,
        "testnet": is_testnet,
        "rest_base_url": "https://testnet.binance.vision" if is_testnet else "https://api.binance.com",
        "ws_url": "wss://stream.testnet.binance.vision/ws" if is_testnet else "wss://stream.binance.com:9443/ws",
    }


def _build_okx_config(trading_mode: str) -> Dict[str, Any]:
    api_key = os.environ.get("OKX_API_KEY", "")
    api_secret = os.environ.get("OKX_API_SECRET", "")
    passphrase = os.environ.get("OKX_PASSPHRASE", "")

    if not api_key or not api_secret or not passphrase:
        raise ValueError(
            "缺少 OKX API 密钥，请设置 OKX_API_KEY、OKX_API_SECRET 和 OKX_PASSPHRASE 环境变量"
        )

    is_testnet = trading_mode == "testnet"
    return {
        "exchange": "okx",
        "api_key": api_key,
        "api_secret": api_secret,
        "passphrase": passphrase,
        "testnet": is_testnet,
        "rest_base_url": "https://www.okx.com",
        "ws_url": "wss://wspap.okx.com:8443/ws/v5/public?brokerId=9999" if is_testnet else "wss://ws.okx.com:8443/ws/v5/public",
    }
