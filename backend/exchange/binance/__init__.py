"""
Binance交易所模块

提供Binance交易所的完整实现。

主要组件:
    - BinanceClient: REST API客户端
    - BinanceWebSocketManager: WebSocket管理器
    - PaperTradingAccount: 模拟交易账户
    - BinanceDownloader: 数据下载器
    - BinanceExchange: 交易所连接器
    - live_adapter: 实盘交易适配器模块

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

# 从 live_adapter 导入实盘交易相关组件
try:
    from .live_adapter import (
        BinanceAccountType,
        BinanceEnvironment,
        BinanceAdapterConfig,
        BinanceDataClientFactory,
        BinanceExecClientFactory,
        build_binance_data_config,
        build_binance_exec_config,
        get_binance_venue,
        resolve_binance_account_type,
        resolve_binance_environment,
        validate_binance_credentials,
        create_binance_config_from_dict,
        # 异常类
        BinanceAdapterError,
        BinanceConfigError,
        BinanceCredentialError,
        BinanceClientError,
    )
    LIVE_ADAPTER_AVAILABLE = True
except ImportError:
    LIVE_ADAPTER_AVAILABLE = False

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

# 如果 live_adapter 可用，添加到导出列表
if LIVE_ADAPTER_AVAILABLE:
    __all__.extend([
        "BinanceAccountType",
        "BinanceEnvironment",
        "BinanceAdapterConfig",
        "BinanceDataClientFactory",
        "BinanceExecClientFactory",
        "build_binance_data_config",
        "build_binance_exec_config",
        "get_binance_venue",
        "resolve_binance_account_type",
        "resolve_binance_environment",
        "validate_binance_credentials",
        "create_binance_config_from_dict",
        "BinanceAdapterError",
        "BinanceConfigError",
        "BinanceCredentialError",
        "BinanceClientError",
    ])
