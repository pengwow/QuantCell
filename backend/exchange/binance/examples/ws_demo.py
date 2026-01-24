import asyncio
import logging
import ssl
from binance_common.configuration import ConfigurationWebSocketAPI
from binance_sdk_spot.spot import Spot
from binance_sdk_spot.websocket_api.models import exchange_info_response_result
from zbot.common.config import read_config
# 设置日志级别
logging.basicConfig(level=logging.INFO)
config = read_config('exchange')

# 创建不验证SSL证书的上下文
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

configuration_ws_api = ConfigurationWebSocketAPI(
    api_key=config["binance"]["api_key"], api_secret=config["binance"]["secret_key"],
    proxy={
        "host": "127.0.0.1",
        "port": 7890,
        "protocol": "http",  # or 'https'
    },
    https_agent=ssl_context,
)

client = Spot(config_ws_api=configuration_ws_api)

async def exchange_info():
    connection = None
    try:
        connection = await client.websocket_api.create_connection()

        response = await client.websocket_api.exchange_info(
            symbol="BNBUSDT",
        )

        rate_limits = response.rate_limits
        logging.info(f"exchange_info() rate limits: {rate_limits}")

        data: exchange_info_response_result = response.data()
        logging.info(f"exchange_info() response: {data}")
    except Exception as e:
        logging.error(f"exchange_info() error: {e}")
    finally:
        if connection:
            await connection.close_connection(close_session=True)

if __name__ == "__main__":
    asyncio.run(exchange_info())