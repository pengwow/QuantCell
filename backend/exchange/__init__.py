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

from exchange.base import BaseExchange, CryptoBaseCollector

# 向后兼容：Exchange别名
Exchange = BaseExchange
from exchange.types import (
    # 枚举类型
    OrderSide,
    OrderType,
    OrderStatus,
    TimeInForce,
    TradingMode,
    MarginMode,
    KlineInterval,
    # 数据类
    Ticker,
    OHLCV,
    OrderBookLevel,
    OrderBook,
    Balance,
    Order,
    Trade,
    AccountInfo,
    Position,
    FundingRate,
    StakingProduct,
    SubAccount,
    # 类型别名
    ExchangeFeatures,
    Tickers,
    Balances,
    OHLCVList,
    OrderList,
    TradeList,
    PositionList,
)
from exchange.exceptions import (
    ExchangeError,
    ConnectionError,
    AuthenticationError,
    RateLimitError,
    OrderError,
    InsufficientFundsError,
    InvalidOrderError,
    OrderNotFoundError,
    MarketError,
    SymbolNotFoundError,
    NotImplementedFeatureError,
    TemporaryError,
    DDosProtection,
    NetworkError,
    ConfigurationError,
)
from exchange.decorators import (
    api_retry,
    require_feature,
    require_connected,
    log_api_call,
    rate_limit,
)
from exchange.binance.downloader import BinanceDownloader, BinanceCollector
from exchange.okx.downloader import OKXDownloader, OKXCollector


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
        'binance': _get_binance_exchange(),
        'okx': _get_okx_exchange(),
    }
    
    exchange_name = exchange_name.lower()
    if exchange_name not in exchanges:
        raise ValueError(
            f"不支持的交易所: {exchange_name}。"
            f"支持的交易所: {list(exchanges.keys())}"
        )
    
    return exchanges[exchange_name](**kwargs)


__all__ = [
    # 基类
    'BaseExchange',
    'CryptoBaseCollector',
    # 工厂函数
    'create_exchange',
    # 下载器和收集器
    'BinanceDownloader',
    'BinanceCollector',
    'OKXDownloader',
    'OKXCollector',
    # 枚举类型
    'OrderSide',
    'OrderType',
    'OrderStatus',
    'TimeInForce',
    'TradingMode',
    'MarginMode',
    'KlineInterval',
    # 数据类
    'Ticker',
    'OHLCV',
    'OrderBookLevel',
    'OrderBook',
    'Balance',
    'Order',
    'Trade',
    'AccountInfo',
    'Position',
    'FundingRate',
    'StakingProduct',
    'SubAccount',
    # 类型别名
    'ExchangeFeatures',
    'Tickers',
    'Balances',
    'OHLCVList',
    'OrderList',
    'TradeList',
    'PositionList',
    # 异常类
    'ExchangeError',
    'ConnectionError',
    'AuthenticationError',
    'RateLimitError',
    'OrderError',
    'InsufficientFundsError',
    'InvalidOrderError',
    'OrderNotFoundError',
    'MarketError',
    'SymbolNotFoundError',
    'NotImplementedFeatureError',
    'TemporaryError',
    'DDosProtection',
    'NetworkError',
    'ConfigurationError',
    # 装饰器
    'api_retry',
    'require_feature',
    'require_connected',
    'log_api_call',
    'rate_limit',
]
