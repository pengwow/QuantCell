"""
交易所模块

提供统一的交易所接口和实现。

主要组件:
    - BaseExchange: 交易所抽象基类
    - BinanceExchange: Binance交易所实现
    - OKXExchange: OKX交易所实现
    - 数据模型: Order, Ticker, Balance等
    - 异常类: ExchangeError, OrderError等

使用示例:
    >>> from exchange import create_exchange
    >>> exchange = create_exchange('binance', api_key='xxx', secret_key='xxx')
    >>> exchange.connect()
    >>> balance = exchange.get_balance('BTC')

作者: QuantCell Team
版本: 1.0.0
日期: 2026-02-12
"""

import warnings

from exchange.base import BaseExchange, CryptoBaseCollector


# 向后兼容：Exchange别名（带弃用警告）
def _exchange_init_warning(self, *args, **kwargs):
    """
    .. deprecated:: 2.1
        请使用 BaseExchange 替代
    """
    warnings.warn(
        "Exchange 类名已弃用（v2.1），请使用 BaseExchange",
        DeprecationWarning,
        stacklevel=2,
    )
    BaseExchange.__init__(self, *args, **kwargs)


Exchange = type(
    "Exchange",
    (BaseExchange,),
    {
        "__module__": "exchange",
        "__doc__": ".. deprecated:: 2.1\n\n    请使用 :class:`BaseExchange` 替代",
        "__init__": _exchange_init_warning,
    },
)
from exchange.binance.downloader import BinanceCollector, BinanceDownloader
from exchange.connection import (
    SUPPORTED_EXCHANGES,
    test_exchange_connection,
    test_exchange_connection_sync,
)
from exchange.decorators import (
    api_retry,
    log_api_call,
    rate_limit,
    require_connected,
    require_feature,
)
from exchange.exceptions import (
    AuthenticationError,
    ConfigurationError,
    ConnectionError,
    DDosProtection,
    ExchangeError,
    InsufficientFundsError,
    InvalidOrderError,
    MarketError,
    NetworkError,
    NotImplementedFeatureError,
    OrderError,
    OrderNotFoundError,
    RateLimitError,
    SymbolNotFoundError,
    TemporaryError,
)
from exchange.okx.downloader import OKXCollector, OKXDownloader
from exchange.types import (
    OHLCV,
    AccountInfo,
    Balance,
    Balances,
    ConnectionStatus,
    ConnectionTestResult,
    # 类型别名
    ExchangeFeatures,
    FundingRate,
    KlineInterval,
    MarginMode,
    OHLCVList,
    Order,
    OrderBook,
    OrderBookLevel,
    OrderList,
    # 枚举类型
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    PositionList,
    StakingProduct,
    SubAccount,
    # 数据类
    Ticker,
    Tickers,
    TimeInForce,
    Trade,
    TradeList,
    TradingMode,
)


def _get_binance_exchange():
    from exchange.binance.exchange import BinanceExchange

    return BinanceExchange


def _get_okx_exchange():
    from exchange.okx.exchange import OkxExchange

    return OkxExchange


def create_exchange(exchange_name: str, **kwargs) -> BaseExchange:
    """
    创建交易所实例

    Args:
        exchange_name: 交易所名称，支持 'binance', 'okx'
        **kwargs: 交易所配置参数

    Returns:
        BaseExchange: 交易所实例

    Raises:
        ValueError: 当交易所不支持时

    Example:
        >>> exchange = create_exchange('binance', api_key='xxx', secret_key='xxx')
        >>> exchange.connect()
    """
    exchanges = {
        "binance": _get_binance_exchange(),
        "okx": _get_okx_exchange(),
    }

    exchange_name = exchange_name.lower()
    if exchange_name not in exchanges:
        msg = f"不支持的交易所: {exchange_name}。支持的交易所: {list(exchanges.keys())}"
        raise ValueError(msg)

    return exchanges[exchange_name](**kwargs)


__all__ = [
    "OHLCV",
    "SUPPORTED_EXCHANGES",
    "AccountInfo",
    "AuthenticationError",
    "Balance",
    "Balances",
    # 基类
    "BaseExchange",
    "BinanceCollector",
    # 下载器和收集器
    "BinanceDownloader",
    "ConfigurationError",
    "ConnectionError",
    "ConnectionStatus",
    "ConnectionTestResult",
    "CryptoBaseCollector",
    "DDosProtection",
    # 异常类
    "ExchangeError",
    # 类型别名
    "ExchangeFeatures",
    "FundingRate",
    "InsufficientFundsError",
    "InvalidOrderError",
    "KlineInterval",
    "MarginMode",
    "MarketError",
    "NetworkError",
    "NotImplementedFeatureError",
    "OHLCVList",
    "OKXCollector",
    "OKXDownloader",
    "Order",
    "OrderBook",
    "OrderBookLevel",
    "OrderError",
    "OrderList",
    "OrderNotFoundError",
    # 枚举类型
    "OrderSide",
    "OrderStatus",
    "OrderType",
    "Position",
    "PositionList",
    "RateLimitError",
    "StakingProduct",
    "SubAccount",
    "SymbolNotFoundError",
    "TemporaryError",
    # 数据类
    "Ticker",
    "Tickers",
    "TimeInForce",
    "Trade",
    "TradeList",
    "TradingMode",
    # 装饰器
    "api_retry",
    # 工厂函数
    "create_exchange",
    "log_api_call",
    "rate_limit",
    "require_connected",
    "require_feature",
    # 连通性测试
    "test_exchange_connection",
    "test_exchange_connection_sync",
]
