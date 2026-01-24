import asyncio
import logging
import ssl

import certifi
import websockets
try:
    import python_socks
except ImportError:
    python_socks = None

logger = logging.getLogger(__name__)


class CustomWebSocketFactory:

    def __init__(self, url, proxy_host=None, proxy_port=None, proxy_type=None):
        self.url = url
        self.websocket = None
        self.loop = asyncio.get_event_loop()
        self.proxy_host = proxy_host
        self.proxy_port = proxy_port
        self.proxy_type = proxy_type

    async def connect(self):
        ssl_context = ssl.create_default_context()
        ssl_context.load_verify_locations(certifi.where())
        
        # 如果没有配置代理，直接连接
        if not self.proxy_host or not self.proxy_port or not self.proxy_type:
            try:
                self.websocket = await websockets.connect(self.url, ssl=ssl_context)
                logger.info("WebSocket connection established (no proxy).")
                return self.websocket
            except Exception as e:
                logger.error(f"Error connecting to WebSocket: {e}")
                return None
        
        # 处理HTTP代理
        if self.proxy_type == "http":
            try:
                # 对于HTTP代理，我们需要使用代理URL而不是extra_headers
                proxy_url = f"http://{self.proxy_host}:{self.proxy_port}"
                self.websocket = await websockets.connect(
                    self.url,
                    proxy=proxy_url,
                    ssl=ssl_context
                )
                logger.info("WebSocket connection established (HTTP proxy).")
                return self.websocket
            except Exception as e:
                logger.error(f"Error connecting to WebSocket with HTTP proxy: {e}")
                return None
        
        # 处理SOCKS5代理
        if self.proxy_type == "socks5":
            if not python_socks:
                logger.error("python-socks is required to use a SOCKS proxy")
                return None
            
            try:
                # 创建SOCKS5代理连接
                proxy = python_socks.Proxy.create(
                    proxy_type=python_socks.ProxyType.SOCKS5,
                    host=self.proxy_host,
                    port=self.proxy_port,
                    username=None,
                    password=None
                )
                
                # 通过代理连接WebSocket
                sock = await proxy.connect(self.url.split('/')[2].split(':')[0], 443)
                self.websocket = await websockets.connect(self.url, sock=sock, ssl=ssl_context)
                logger.info("WebSocket connection established (SOCKS5 proxy).")
                return self.websocket
            except Exception as e:
                logger.error(f"Error connecting to WebSocket with SOCKS5 proxy: {e}")
                return None
        
        # 未知代理类型
        logger.error(f"Unknown proxy type: {self.proxy_type}")
        return None

    async def close(self):
        if self.websocket:
            await self.websocket.close()
            self.websocket = None