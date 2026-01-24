import asyncio
import logging
import ssl
from binance_common.configuration import ConfigurationWebSocketStreams
from binance_common.constants import DERIVATIVES_TRADING_USDS_FUTURES_WS_STREAMS_PROD_URL
from binance_sdk_derivatives_trading_usds_futures.derivatives_trading_usds_futures import DerivativesTradingUsdsFutures

logging.basicConfig(level=logging.INFO)
# 创建不验证SSL证书的上下文
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

configuration_ws_streams = ConfigurationWebSocketStreams(
    reconnect_delay=5000,
    proxy={
        "host": "127.0.0.1",
        "port": 7890,
        "protocol": "http",  # or 'https'
    },
    https_agent=ssl_context,
)

client = DerivativesTradingUsdsFutures(config_ws_streams=configuration_ws_streams)

def callback(data):
    print(f"all_book_tickers_stream() message: {data}")

async def all_book_tickers_stream():
    connection = None
    try:
        connection = await client.websocket_streams.create_connection()

        stream = await connection.all_book_tickers_stream()
        stream.on("message", callback)
        await asyncio.sleep(10)
    except Exception as e:
        logging.error(f"all_book_tickers_stream() error: {e}")
    finally:
        if connection:
            await connection.close_connection(close_session=True)


if __name__ == "__main__":
    asyncio.run(all_book_tickers_stream())