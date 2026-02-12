"""
Binance交易所连接模块

基于python-binance库实现的Binance交易所连接功能，包括：
- REST API客户端
- WebSocket实时数据
- 模拟盘交易
"""

from .client import BinanceClient
from .websocket_manager import BinanceWebSocketManager
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

__version__ = "1.0.0"
