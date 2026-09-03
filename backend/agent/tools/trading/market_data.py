"""市场数据工具 - 薄封装，调用CLI层"""

from typing import Any

from ..base import Tool


class GetKlinesTool(Tool):
    """获取 K 线数据"""

    name = "get_klines"
    description = "获取指定交易对的 K 线（蜡烛图）数据。支持多个交易所。"
    parameters = {
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "交易对，如 BTCUSDT"},
            "timeframe": {
                "type": "string",
                "description": "时间周期，如 1m, 5m, 1h, 1d",
                "enum": [
                    "1m",
                    "3m",
                    "5m",
                    "15m",
                    "30m",
                    "1h",
                    "2h",
                    "4h",
                    "6h",
                    "8h",
                    "12h",
                    "1d",
                    "3d",
                    "1w",
                    "1M",
                ],
            },
            "limit": {
                "type": "integer",
                "description": "返回条数（最大 1000）",
                "minimum": 1,
                "maximum": 1000,
                "default": 100,
            },
            "exchange": {
                "type": "string",
                "description": "交易所，如 binance, okx",
                "default": "binance",
            },
        },
        "required": ["symbol", "timeframe"],
    }

    async def execute(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 100,
        exchange: str = "binance",
        **kwargs: Any,
    ) -> str:
        from cli.market import get_klines

        return get_klines(symbol, timeframe, limit, exchange)


class GetTickerTool(Tool):
    """获取最新行情"""

    name = "get_ticker"
    description = "获取指定交易对的最新行情数据（最新价、涨跌幅等）。"
    parameters = {
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "交易对，如 BTCUSDT"},
            "exchange": {
                "type": "string",
                "description": "交易所",
                "default": "binance",
            },
        },
        "required": ["symbol"],
    }

    async def execute(self, symbol: str, exchange: str = "binance", **kwargs: Any) -> str:
        from cli.market import get_ticker

        return get_ticker(symbol, exchange)


class GetCryptoSymbolsTool(Tool):
    """获取交易对列表"""

    name = "get_crypto_symbols"
    description = "获取交易所支持的加密货币交易对列表。"
    parameters = {
        "type": "object",
        "properties": {
            "exchange": {
                "type": "string",
                "description": "交易所名称，如 binance",
                "default": "binance",
            },
            "filter": {"type": "string", "description": "过滤条件，如 USDT"},
            "limit": {"type": "integer", "description": "返回数量", "default": 100},
            "market_type": {
                "type": "string",
                "description": "市场类型：spot(现货)/future(合约)",
                "default": "spot",
            },
        },
        "required": [],
    }
    param_template = {}

    async def execute(
        self,
        exchange: str = "binance",
        filter: str = "USDT",
        limit: int = 100,
        market_type: str = "spot",
        **kwargs: Any,
    ) -> str:
        from cli.market import get_crypto_symbols

        return get_crypto_symbols(exchange, filter, limit, market_type)


class FetchMarketDataTool(Tool):
    """获取市场数据"""

    name = "fetch_market_data"
    description = "获取实时或历史市场数据。支持K线(OHLCV)、24小时行情、订单簿等数据类型。"
    parameters = {
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "交易对，如 BTCUSDT"},
            "data_type": {
                "type": "string",
                "description": "数据类型：kline(K线)、24h_ticker(24小时行情)",
                "enum": ["kline", "24h_ticker"],
            },
            "interval": {
                "type": "string",
                "description": "K线时间周期(仅kline类型需要)，如1m,5m,15m,1h,4h,1d",
                "default": "1h",
            },
            "limit": {
                "type": "integer",
                "description": "返回数据条数(仅kline类型需要)",
                "default": 100,
            },
            "market_type": {
                "type": "string",
                "description": "市场类型：spot(现货)/future(合约)",
                "default": "spot",
            },
        },
        "required": ["symbol", "data_type"],
    }
    param_template = {}

    async def execute(
        self,
        symbol: str,
        data_type: str,
        interval: str = "1h",
        limit: int = 100,
        market_type: str = "spot",
        **kwargs: Any,
    ) -> str:
        from cli.market import fetch_market_data

        return fetch_market_data(symbol, data_type, interval, limit, market_type)
