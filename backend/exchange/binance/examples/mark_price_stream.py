import asyncio
import os
import logging
import ssl
from binance_common.models import WebsocketApiResponse
from binance_sdk_derivatives_trading_usds_futures.derivatives_trading_usds_futures import (
    DerivativesTradingUsdsFutures,
    DERIVATIVES_TRADING_USDS_FUTURES_WS_STREAMS_PROD_URL,
    ConfigurationWebSocketStreams,
)

# 创建不验证SSL证书的上下文
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

# Configure logging
logging.basicConfig(level=logging.INFO)

# Create configuration for the WebSocket Streams
configuration_ws_streams = ConfigurationWebSocketStreams(
    reconnect_delay=2000,
    stream_url=os.getenv(
        "STREAM_URL", DERIVATIVES_TRADING_USDS_FUTURES_WS_STREAMS_PROD_URL
    ),
    proxy={
        "host": "127.0.0.1",
        "port": 7890,
        "protocol": "http",  # or 'https'
    },
    https_agent=ssl_context,
)

# Initialize DerivativesTradingUsdsFutures client
client = DerivativesTradingUsdsFutures(config_ws_streams=configuration_ws_streams)

# Global variables for connection management
connection = None
stream = None


def callback(message: WebsocketApiResponse):
    """
    WebSocket 回调函数
    
    Args:
        message (WebsocketApiResponse): WebSocket 响应数据
    """
    print(f"事件类型{message.e}")
    # logging.info(f"mark_price_stream() message: {message}")
    if message.k.x:
        print(f"k线结束数据{message.k}")
    # 检查是否为监听密钥过期事件
    if message.e == "listenKeyExpired":
        logging.warning(f"监听密钥已过期: {message.listenKey}")
        # 启动重新连接任务
        asyncio.create_task(reconnect())


async def reconnect():
    """
    重新建立 WebSocket 连接
    """
    global connection, stream
    logging.info("开始重新连接 WebSocket...")
    
    try:
        # 关闭现有连接
        if connection:
            await connection.close_connection(close_session=True)
    except Exception as e:
        logging.error(f"关闭现有连接时出错: {e}")
    
    try:
        # 创建新连接
        connection = await client.websocket_streams.create_connection()
        
        # 重新订阅数据流
        stream = await connection.mark_price_stream(
            symbol="btcusdt",
        )
        stream.on("message", callback)
        
        logging.info("WebSocket 重新连接成功")
    except Exception as e:
        logging.error(f"重新连接 WebSocket 时出错: {e}")


async def mark_price_stream():
    """
    启动标记价格数据流
    """
    global connection, stream
    try:
        connection = await client.websocket_streams.create_connection()

        stream = await connection.kline_candlestick_streams(
            symbol="btcusdt",
            interval="1m",
        )
        stream.on("message", callback)

        # 保持连接运行
        while True:
            await asyncio.sleep(1)
    except Exception as e:
        logging.error(f"mark_price_stream() error: {e}")
    finally:
        if connection:
            await connection.close_connection(close_session=True)


if __name__ == "__main__":
    try:
        asyncio.run(mark_price_stream())
    except KeyboardInterrupt:
        logging.info("程序被用户中断")
    except Exception as e:
        logging.error(f"程序运行出错: {e}")