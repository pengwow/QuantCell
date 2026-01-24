import asyncio
import logging

from binance_common.configuration import ConfigurationWebSocketStreams
from binance_sdk_derivatives_trading_usds_futures.derivatives_trading_usds_futures import DerivativesTradingUsdsFutures
config = read_config('exchange')

# 创建不验证SSL证书的上下文
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

logging.basicConfig(level=logging.INFO)

configuration_ws_streams = ConfigurationWebSocketStreams(
    reconnect_delay=5000,
    api_key=config["binance"]["api_key"], api_secret=config["binance"]["secret_key"],
    proxy={
        "host": "127.0.0.1",
        "port": 7890,
        "protocol": "http",  # or 'https'
    },
    https_agent=ssl_context,
)

client = DerivativesTradingUsdsFutures(config_ws_streams=configuration_ws_streams)


async def allBookTickersStream():
    connection = None
    try:
        connection = await client.websocket_streams.create_connection()

        stream = await connection.allBookTickersStream()
        stream.on("message", lambda data: print(f"{data}"))
        await asyncio.sleep(5)
    except Exception as e:
        logging.error(f"allBookTickersStream() error: {e}")
    finally:
        if connection:
            await connection.close_connection(close_session=True)


if __name__ == "__main__":
    asyncio.run(allBookTickersStream())