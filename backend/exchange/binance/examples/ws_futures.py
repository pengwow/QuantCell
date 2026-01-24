import logging
from binance_common.configuration import ConfigurationRestAPI
from binance_common.constants import DERIVATIVES_TRADING_USDS_FUTURES_REST_API_TESTNET_URL, DERIVATIVES_TRADING_USDS_FUTURES_REST_API_PROD_URL
from binance_sdk_derivatives_trading_usds_futures.derivatives_trading_usds_futures import DerivativesTradingUsdsFutures
from binance_sdk_derivatives_trading_usds_futures.rest_api.models import ExchangeInformationResponse, AllOrdersResponse
from zbot.common.config import read_config
config = read_config('exchange')

logging.basicConfig(level=logging.INFO)
configuration = ConfigurationRestAPI(api_key=config["binance"]["api_key"], api_secret=config["binance"]["secret_key"], base_path=DERIVATIVES_TRADING_USDS_FUTURES_REST_API_TESTNET_URL)

client = DerivativesTradingUsdsFutures(config_rest_api=configuration)

try:
    # response = client.rest_api.exchange_information()

    # data: ExchangeInformationResponse = response.data()
    # logging.info(f"exchange_information() response: {data}")
    # response = client.rest_api.all_orders(symbol="BTCUSDT")
    # order_data: AllOrdersResponse = response.data()
    # logging.info(f"all_orders() response: {order_data}")
    response = client.rest_api.futures_account_balance_v3()
    order_book_data = response.data()
    logging.info(f"futures_account_balance_v3() response: {order_book_data}")
except Exception as e:
    logging.error(f"exchange_information() error: {e}")