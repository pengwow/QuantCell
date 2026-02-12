"""
Binance模块自定义异常类
"""


class BinanceError(Exception):
    """Binance模块基础异常"""
    pass


class BinanceConnectionError(BinanceError):
    """连接错误"""
    def __init__(self, message: str, url: str = None):
        self.url = url
        super().__init__(message)


class BinanceAPIError(BinanceError):
    """API调用错误"""
    def __init__(self, message: str, code: int = None, response: dict = None):
        self.code = code
        self.response = response
        super().__init__(message)


class BinanceWebSocketError(BinanceError):
    """WebSocket错误"""
    def __init__(self, message: str, connection_id: str = None):
        self.connection_id = connection_id
        super().__init__(message)


class BinanceOrderError(BinanceError):
    """订单操作错误"""
    def __init__(self, message: str, order_id: str = None, symbol: str = None):
        self.order_id = order_id
        self.symbol = symbol
        super().__init__(message)


class BinanceAuthenticationError(BinanceError):
    """认证错误"""
    pass


class BinanceRateLimitError(BinanceError):
    """速率限制错误"""
    def __init__(self, message: str, retry_after: int = None):
        self.retry_after = retry_after
        super().__init__(message)
