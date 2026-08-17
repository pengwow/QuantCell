"""
数据采集服务模块

提供数据采集相关的业务服务。

服务列表:
    - DataService: 数据服务
    - CryptoSymbolService: 加密货币币种服务
    - sync_crypto_symbols: 加密货币对同步函数
    - GetData: 数据下载工具
    - ExportData: 数据导出工具
    - KlineDataFactory: K线数据工厂
    - KlineHealthChecker: K线数据健康检查服务
    - ProductListFactory: 产品列表工厂
    - SystemService: 系统服务
    - MarketDataService: 市场数据服务
    - MarketDataFetcherFactory: 市场数据获取器工厂
"""

from .archive_service import ArchiveService
from .data_service import DataService, CryptoSymbolService, sync_crypto_symbols, GetData, ExportData
from .kline_factory import KlineDataFactory
from .kline_health_service import KlineHealthChecker
from .product_factory import ProductListFactory
from .system_service import SystemService
from .market_data_service import market_data_service
from .market_data_factory import (
    MarketDataFetcherFactory,
    MarketDataFetcher,
    BinanceMarketDataFetcher,
    OKXMarketDataFetcher,
    BybitMarketDataFetcher,
)
from .exchange_connection_service import (
    ExchangeConnectionService,
    exchange_connection_service,
    ConnectionTestResult,
    ConnectionStatus,
)

__all__ = [
    "ArchiveService",
    "CryptoSymbolService",
    "DataService",
    "KlineDataFactory",
    "KlineHealthChecker",
    "ProductListFactory",
    "SystemService",
    "market_data_service",
    "MarketDataFetcherFactory",
    "MarketDataFetcher",
    "BinanceMarketDataFetcher",
    "OKXMarketDataFetcher",
    "BybitMarketDataFetcher",
    "ExchangeConnectionService",
    "exchange_connection_service",
    "ConnectionTestResult",
    "ConnectionStatus",
]
