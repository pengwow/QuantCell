import asyncio
import logging
import ssl
from typing import Callable, Optional

from binance_common.models import WebsocketApiResponse
from binance_sdk_derivatives_trading_usds_futures.derivatives_trading_usds_futures import (
    DerivativesTradingUsdsFutures,
    DERIVATIVES_TRADING_USDS_FUTURES_WS_STREAMS_PROD_URL,
    ConfigurationWebSocketStreams,
)


class BinanceWebSocketConnector:
    """
    Binance WebSocket 连接器，用于管理 WebSocket 连接和自动重连
    
    支持不同的数据流方法，如 mark_price_stream, kline_stream 等。
    通过 connect 方法指定流方法名和参数进行连接。
    """

    def __init__(self, api_key: str = None, secret_key: str = None, proxy: dict = None):
        """
        初始化 Binance WebSocket 连接器
        
        Args:
            api_key (str, optional): API 密钥
            secret_key (str, optional): 密钥
            proxy (dict, optional): 代理配置
        """
        # 创建不验证SSL证书的上下文
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        # Create configuration for the WebSocket Streams
        self.configuration_ws_streams = ConfigurationWebSocketStreams(
            stream_url=DERIVATIVES_TRADING_USDS_FUTURES_WS_STREAMS_PROD_URL,
            proxy=proxy,
            https_agent=ssl_context,
        )

        # Initialize DerivativesTradingUsdsFutures client
        self.client = DerivativesTradingUsdsFutures(
            config_ws_streams=self.configuration_ws_streams,
            config_rest_api=None  # 如果需要 REST API，可以添加配置
        )
        
        # 连接相关变量
        self.connection = None
        self.stream = None
        self._user_callback: Optional[Callable] = None
        self._stream_method: Optional[str] = None
        self._stream_kwargs: Optional[dict] = None
        
        # 配置日志
        self.logger = logging.getLogger(__name__)

    def set_callback(self, callback: Callable[[WebsocketApiResponse], None]):
        """
        设置 WebSocket 回调函数
        
        Args:
            callback (Callable[[WebsocketApiResponse], None]): 回调函数
            
        Returns:
            None
        """
        self._user_callback = callback

    def _internal_callback(self, data: WebsocketApiResponse):
        """
        内部 WebSocket 回调函数，处理连接相关事件
        
        Args:
            data (WebsocketApiResponse): WebSocket 响应数据
            
        Returns:
            None
            
        Raises:
            Exception: 用户回调函数执行出错时抛出
        """
        # 调用用户回调函数
        if self._user_callback:
            try:
                self._user_callback(data)
            except Exception as e:
                self.logger.error(f"用户回调函数执行出错: {e}")
        
        # 检查是否为监听密钥过期事件
        if data.e == "listenKeyExpired":
            self.logger.warning(f"监听密钥已过期: {data.listenKey}")
            # 启动重新连接任务
            asyncio.create_task(self.reconnect())

    async def connect(self, stream_method: str, **kwargs):
        """
        建立 WebSocket 连接并订阅指定的数据流
        
        Args:
            stream_method (str): 数据流方法名
            **kwargs: 传递给数据流方法的参数
            
        Returns:
            None
            
        Raises:
            Exception: WebSocket 连接失败时抛出
        """
        try:
            self.connection = await self.client.websocket_streams.create_connection()
            # 使用 getattr 获取连接对象上的方法，并调用它
            method = getattr(self.connection, stream_method)
            self.stream = await method(**kwargs)
            self.stream.on("message", self._internal_callback)
            self.logger.info(f"WebSocket 连接成功，订阅数据流方法: {stream_method}")
            
            # 保存连接信息，用于重新连接
            self._stream_method = stream_method
            self._stream_kwargs = kwargs
        except Exception as e:
            self.logger.error(f"WebSocket 连接失败: {e}")
            raise

    async def reconnect(self):
        """
        重新建立 WebSocket 连接
        
        Returns:
            None
            
        Raises:
            Exception: 重新连接 WebSocket 时出错时抛出
        """
        self.logger.info("开始重新连接 WebSocket...")
        
        try:
            # 关闭现有连接
            if self.connection:
                await self.connection.close_connection(close_session=True)
        except Exception as e:
            self.logger.error(f"关闭现有连接时出错: {e}")
        
        try:
            # 创建新连接
            self.connection = await self.client.websocket_streams.create_connection()
            
            # 重新订阅数据流（需要保存原始订阅信息）
            # 注意：这里需要在调用 connect 时保存 stream_method 和 kwargs
            if hasattr(self, '_stream_method') and hasattr(self, '_stream_kwargs'):
                method = getattr(self.connection, self._stream_method)
                self.stream = await method(**self._stream_kwargs)
                self.stream.on("message", self._internal_callback)
            else:
                self.logger.warning("未找到原始订阅信息，无法重新订阅数据流")
            
            self.logger.info("WebSocket 重新连接成功")
        except Exception as e:
            self.logger.error(f"重新连接 WebSocket 时出错: {e}")

    async def disconnect(self):
        """
        断开 WebSocket 连接
        
        Returns:
            None
            
        Raises:
            Exception: 断开 WebSocket 连接时出错时抛出
        """
        try:
            if self.stream:
                await self.stream.unsubscribe()
            if self.connection:
                await self.connection.close_connection(close_session=True)
            self.logger.info("WebSocket 连接已断开")
        except Exception as e:
            self.logger.error(f"断开 WebSocket 连接时出错: {e}")

    async def run_forever(self):
        """
        保持 WebSocket 连接运行
        
        Returns:
            None
            
        Raises:
            asyncio.CancelledError: WebSocket 运行任务被取消时抛出
        """
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            self.logger.info("WebSocket 运行任务被取消")
            await self.disconnect()