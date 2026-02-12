"""
Binance交易所模块

提供Binance交易所的完整实现。

主要组件:
    - BinanceClient: REST API客户端
    - BinanceWebSocketManager: WebSocket管理器
    - PaperTradingAccount: 模拟交易账户
    - BinanceDownloader: 数据下载器
    - BinanceExchange: 交易所连接器

作者: QuantCell Team
版本: 1.0.0
日期: 2026-02-12
"""

from .client import BinanceClient
from .websocket import BinanceWebSocketManager
from .paper_trading import PaperTradingAccount
from .exceptions import (
    BinanceConnectionError,
    BinanceAPIError,
    BinanceWebSocketError,
    BinanceOrderError,
)
from .config import BinanceConfig

__all__ = [
    "BinanceClient",
    "BinanceWebSocketManager",
    "PaperTradingAccount",
    "BinanceConnectionError",
    "BinanceAPIError",
    "BinanceWebSocketError",
    "BinanceOrderError",
    "BinanceConfig",
]
