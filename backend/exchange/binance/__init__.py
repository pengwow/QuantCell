from typing import Optional
from .connector import BinanceExchange
# from .connector import AsyncBinanceExchange
from .websocket_connector import BinanceWebSocketConnector


# def create_async_connector(api_key: Optional[str] = None, secret_key: Optional[str] = None, proxy_url: Optional[str] = None, testnet: Optional[bool] = None) -> AsyncBinanceExchange:
#     """创建Binance异步连接器实例的工厂函数

#     Args:
#         api_key: 可选的API密钥，未提供则从配置读取
#         secret_key: 可选的密钥，未提供则从配置读取
#         proxy_url: 可选的代理URL
#         testnet: 是否使用测试网络，未提供则从配置读取

#     Returns:
#         配置好的AsyncBinanceExchange实例
#     """
#     return AsyncBinanceExchange(
#         api_key=api_key,
#         secret_key=secret_key,
#         proxy_url=proxy_url,
#         testnet=testnet
#     )