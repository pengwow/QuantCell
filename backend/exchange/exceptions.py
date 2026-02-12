"""
交易所异常定义模块

提供交易所相关的异常类定义。

作者: QuantCell Team
版本: 1.0.0
日期: 2026-02-12
"""

from typing import Optional


class ExchangeError(Exception):
    """
    交易所基础异常
    
    所有交易所异常的基类。
    """
    
    def __init__(self, message: str, exchange_name: Optional[str] = None):
        super().__init__(message)
        self.exchange_name = exchange_name
        self.message = message


class ConnectionError(ExchangeError):
    """
    连接异常
    
    当无法连接到交易所时抛出。
    """
    pass


class AuthenticationError(ExchangeError):
    """
    认证异常
    
    当API密钥无效或认证失败时抛出。
    """
    pass


class RateLimitError(ExchangeError):
    """
    速率限制异常
    
    当超过API调用频率限制时抛出。
    """
    
    def __init__(
        self, 
        message: str, 
        exchange_name: Optional[str] = None,
        retry_after: Optional[int] = None
    ):
        super().__init__(message, exchange_name)
        self.retry_after = retry_after  # 建议重试时间（秒）


class OrderError(ExchangeError):
    """
    订单异常
    
    当订单操作失败时抛出。
    """
    
    def __init__(
        self, 
        message: str, 
        exchange_name: Optional[str] = None,
        order_id: Optional[str] = None,
        symbol: Optional[str] = None
    ):
        super().__init__(message, exchange_name)
        self.order_id = order_id
        self.symbol = symbol


class InsufficientFundsError(OrderError):
    """
    资金不足异常
    
    当账户余额不足以执行订单时抛出。
    """
    pass


class InvalidOrderError(OrderError):
    """
    无效订单异常
    
    当订单参数无效时抛出。
    """
    pass


class OrderNotFoundError(OrderError):
    """
    订单未找到异常
    
    当查询的订单不存在时抛出。
    """
    pass


class MarketError(ExchangeError):
    """
    市场异常
    
    当市场数据获取失败时抛出。
    """
    pass


class SymbolNotFoundError(MarketError):
    """
    交易对未找到异常
    
    当交易对不存在时抛出。
    """
    pass


class NotImplementedFeatureError(ExchangeError):
    """
    功能未实现异常
    
    当交易所不支持特定功能时抛出。
    """
    
    def __init__(
        self, 
        message: str, 
        exchange_name: Optional[str] = None,
        feature: Optional[str] = None
    ):
        super().__init__(message, exchange_name)
        self.feature = feature


class TemporaryError(ExchangeError):
    """
    临时错误异常
    
    当交易所暂时不可用时抛出，可以重试。
    """
    pass


class DDosProtection(TemporaryError):
    """
    DDoS防护异常
    
    当触发交易所DDoS防护时抛出。
    """
    pass


class NetworkError(TemporaryError):
    """
    网络错误异常
    
    当网络连接出现问题时抛出。
    """
    pass


class ConfigurationError(ExchangeError):
    """
    配置错误异常
    
    当交易所配置无效时抛出。
    """
    pass
