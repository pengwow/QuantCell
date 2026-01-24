from binance_common.configuration import ConfigurationRestAPI
from binance_common.constants import SPOT_REST_API_TESTNET_URL, SPOT_REST_API_PROD_URL
from binance_sdk_spot.spot import Spot
from binance_sdk_spot.rest_api.models import ExchangeInfoResponse, RateLimits
from zbot.common.config import read_config

import logging
from typing import List

logging.basicConfig(level=logging.INFO)
config = read_config('exchange')

configuration = ConfigurationRestAPI(api_key=config["binance"]["api_key"], api_secret=config["binance"]["secret_key"],
                                     base_path=SPOT_REST_API_TESTNET_URL)

client = Spot(config_rest_api=configuration)

try:
    # response = client.rest_api.exchange_info(symbol="BNBUSDT")

    # rate_limits: List[RateLimits] = response.rate_limits
    # logging.info(f"exchange_info() rate limits: {rate_limits}")

    # data: ExchangeInfoResponse = response.data()
    # logging.info(f"exchange_info() response: {data}")
    
    response = client.rest_api.get_account()
    logging.info(f"ping() response: {response.data()}")
except Exception as e:
    logging.error(f"ping() error: {e}")
