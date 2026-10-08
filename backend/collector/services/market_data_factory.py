"""市场数据工厂模块

基于工厂模式实现多交易所市场数据获取的统一接口
支持从系统配置读取代理信息
"""

import asyncio
import json
import os
from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal
from typing import Any
from urllib.parse import quote

import aiohttp
from binance import AsyncClient

from utils.logger import LogType, get_logger
from utils.timestamp_utils import utc_now_naive

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)
from collector.db.database import get_db
from collector.db.models import MarketData

# 单次币安请求超时（秒），超时立即失败以便回退数据库缓存
BINANCE_TIMEOUT_SECONDS = 5
# 币安 /ticker/24hr 的 symbols 参数单次上限
BINANCE_MAX_SYMBOLS_PER_REQUEST = 100


class MarketDataFetcher(ABC):
    """市场数据获取器抽象基类

    定义了获取市场数据的统一接口，不同交易所的获取器需要实现此接口
    """

    def __init__(self, exchange_id: str, config: dict[str, Any]):
        """初始化获取器

        Args:
            exchange_id: 交易所ID
            config: 交易所配置字典
        """
        self.exchange_id = exchange_id
        self.config = config
        self.name = config.get("name", exchange_id)
        self.proxy_enabled = config.get("proxy_enabled", False)
        self.proxy_url = config.get("proxy_url", "")
        self.proxy_username = config.get("proxy_username", "")
        self.proxy_password = config.get("proxy_password", "")
        self.api_key = config.get("api_key", "")
        self.api_secret = config.get("api_secret", "")

    @abstractmethod
    async def fetch_market_data(self, symbols: list[str]) -> list[dict[str, Any]]:
        """获取市场数据

        Args:
            symbols: 货币对列表

        Returns:
            List[Dict]: 市场数据列表
        """

    @abstractmethod
    async def fetch_all_tickers(self) -> list[dict[str, Any]]:
        """获取所有货币对的市场数据

        Returns:
            List[Dict]: 市场数据列表
        """

    def _get_proxy_config(self) -> dict[str, str] | None:
        """获取代理配置

        Returns:
            Optional[Dict]: 代理配置字典，如果未启用代理则返回None
        """
        if not self.proxy_enabled or not self.proxy_url:
            return None

        proxy_config = {
            "http": self.proxy_url,
            "https": self.proxy_url,
        }

        # 如果有认证信息，添加到代理URL
        if self.proxy_username and self.proxy_password:
            # 解析URL并添加认证信息
            from urllib.parse import urlparse, urlunparse

            parsed = urlparse(self.proxy_url)
            netloc = f"{self.proxy_username}:{self.proxy_password}@{parsed.netloc}"
            proxy_url_with_auth = urlunparse(
                (
                    parsed.scheme,
                    netloc,
                    parsed.path,
                    parsed.params,
                    parsed.query,
                    parsed.fragment,
                )
            )
            proxy_config = {
                "http": proxy_url_with_auth,
                "https": proxy_url_with_auth,
            }

        return proxy_config

    async def _save_market_data_batch(self, items: list[dict[str, Any]]):
        """批量保存市场数据到数据库（异步包装）

        同步数据库写入会阻塞事件循环，这里通过 to_thread 卸载到线程池执行。

        Args:
            items: 市场数据字典列表
        """
        if not items:
            return
        await asyncio.to_thread(self._save_market_data_batch_sync, items)

    def _save_market_data_batch_sync(self, items: list[dict[str, Any]]):
        """批量保存市场数据的同步实现

        使用单个 session、只提交一次事务，避免逐条 commit 带来的额外开销。

        Args:
            items: 市场数据字典列表
        """
        db = next(get_db())
        try:
            for data in items:
                record = (
                    db.query(MarketData)
                    .filter(
                        MarketData.symbol == data["symbol"],
                        MarketData.exchange == self.exchange_id,
                    )
                    .first()
                )

                if record:
                    # 更新
                    record.price = Decimal(str(data["price"])) if data.get("price") else None
                    record.price_change_24h = (
                        Decimal(str(data["price_change_24h"])) if data.get("price_change_24h") else None
                    )
                    record.price_change_percent_24h = (
                        Decimal(str(data["price_change_percent_24h"])) if data.get("price_change_percent_24h") else None
                    )
                    record.volume_24h = Decimal(str(data["volume_24h"])) if data.get("volume_24h") else None
                    record.high_24h = Decimal(str(data["high_24h"])) if data.get("high_24h") else None
                    record.low_24h = Decimal(str(data["low_24h"])) if data.get("low_24h") else None
                    record.last_update = utc_now_naive()
                else:
                    # 新建
                    db.add(
                        MarketData(
                            symbol=data["symbol"],
                            exchange=self.exchange_id,
                            price=Decimal(str(data["price"])) if data.get("price") else None,
                            price_change_24h=Decimal(str(data["price_change_24h"]))
                            if data.get("price_change_24h")
                            else None,
                            price_change_percent_24h=Decimal(str(data["price_change_percent_24h"]))
                            if data.get("price_change_percent_24h")
                            else None,
                            volume_24h=Decimal(str(data["volume_24h"])) if data.get("volume_24h") else None,
                            high_24h=Decimal(str(data["high_24h"])) if data.get("high_24h") else None,
                            low_24h=Decimal(str(data["low_24h"])) if data.get("low_24h") else None,
                            last_update=utc_now_naive(),
                        )
                    )

            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"批量保存市场数据到数据库失败: {e}")
        finally:
            db.close()


class BinanceMarketDataFetcher(MarketDataFetcher):
    """币安市场数据获取器"""

    def __init__(self, config: dict[str, Any]):
        super().__init__("binance", config)

    async def _get_client(self) -> AsyncClient:
        """创建币安异步客户端

        优先使用数据库配置的代理，其次使用环境变量代理。

        ponytail: 不缓存 client。AsyncClient 内部持有 aiohttp session 并绑定创建时的
        事件循环，跨请求复用会引发 "attached to a different loop"；每次请求新建、
        用后在 finally 中 close_connection，代价可接受。
        """
        # 优先使用数据库配置的代理，其次使用环境变量代理
        proxies = self._get_proxy_config()
        if not proxies:
            env_https = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY")
            env_http = os.environ.get("http_proxy") or os.environ.get("HTTP_PROXY")
            if env_https or env_http:
                proxies = {
                    "http": env_http or env_https,
                    "https": env_https or env_http,
                }
                logger.info(f"使用环境变量代理获取市场数据: {proxies}")

        https_proxy = proxies.get("https") if proxies else None
        logger.info(f"初始化币安异步客户端，代理: {https_proxy is not None}")

        # AsyncClient.create 内部会 ping 校验连通性，不可达时快速失败
        return await AsyncClient.create(
            self.api_key,
            self.api_secret,
            session_params={"timeout": aiohttp.ClientTimeout(total=BINANCE_TIMEOUT_SECONDS)},
            https_proxy=https_proxy,
        )

    def _normalize_symbol(self, symbol: str) -> str:
        """标准化symbol格式

        将 BTC/USDT 转换为 BTCUSDT（币安格式）
        """
        return symbol.replace("/", "")

    def _denormalize_symbol(self, symbol: str) -> str:
        """反标准化symbol格式

        将 BTCUSDT 转换为 BTC/USDT（标准格式）
        """
        # 尝试分离基础货币和计价货币
        # 常见计价货币：USDT, BTC, ETH, BNB, USDC, TUSD, BUSD
        quote_currencies = [
            "USDT",
            "BTC",
            "ETH",
            "BNB",
            "USDC",
            "TUSD",
            "BUSD",
            "DAI",
            "PAX",
            "USDS",
        ]

        for quote_currency in quote_currencies:
            if symbol.endswith(quote_currency):
                base = symbol[: -len(quote_currency)]
                return f"{base}/{quote_currency}"

        # 如果无法识别，直接返回原值
        return symbol

    def _ticker_to_data(self, ticker: dict[str, Any]) -> dict[str, Any]:
        """把币安 ticker 映射为内部市场数据字典

        Args:
            ticker: 币安返回的单条 ticker

        Returns:
            Dict[str, Any]: 内部市场数据字典
        """
        return {
            "symbol": self._denormalize_symbol(ticker["symbol"]),
            "price": float(ticker["lastPrice"]),
            "price_change_24h": float(ticker["priceChange"]),
            "price_change_percent_24h": float(ticker["priceChangePercent"]),
            "volume_24h": float(ticker["volume"]),
            "high_24h": float(ticker["highPrice"]),
            "low_24h": float(ticker["lowPrice"]),
            "last_update": utc_now_naive().isoformat(),
        }

    async def fetch_market_data(self, symbols: list[str]) -> list[dict[str, Any]]:
        """从币安获取市场数据

        使用 /ticker/24hr 的 symbols 参数按块批量请求，替代逐个 symbol 串行请求。

        Args:
            symbols: 货币对列表

        Returns:
            List[Dict]: 市场数据列表
        """
        if not symbols:
            return []

        client = await self._get_client()
        all_data: list[dict[str, Any]] = []
        try:
            normalized = [self._normalize_symbol(s) for s in symbols]
            for i in range(0, len(normalized), BINANCE_MAX_SYMBOLS_PER_REQUEST):
                chunk = normalized[i : i + BINANCE_MAX_SYMBOLS_PER_REQUEST]
                logger.info(f"从币安批量获取市场数据，symbol 数量: {len(chunk)}")
                try:
                    # 币安要求 symbols 传 JSON 数组字符串；python-binance 只对 symbol 的
                    # 值做 urlencode，其它参数原样拼接，故这里必须自行 quote
                    params = quote(json.dumps(chunk, separators=(",", ":")))
                    tickers = await client.get_ticker(symbols=params)
                    # 单个 symbol 时币安返回对象而非列表，统一成列表
                    if isinstance(tickers, dict):
                        tickers = [tickers]
                    all_data.extend(self._ticker_to_data(t) for t in tickers)
                except Exception as e:
                    # 单块失败不影响其余块
                    logger.warning(f"批量获取市场数据失败（块 {i // BINANCE_MAX_SYMBOLS_PER_REQUEST}）: {e}")
                    continue

            if all_data:
                await self._save_market_data_batch(all_data)
            return all_data
        except Exception as e:
            logger.error(f"从币安获取市场数据失败: {e}")
            raise
        finally:
            await client.close_connection()

    async def fetch_all_tickers(self) -> list[dict[str, Any]]:
        """获取所有货币对的市场数据"""
        client = await self._get_client()
        try:
            tickers = await client.get_ticker()
            all_data = [self._ticker_to_data(t) for t in tickers]
            if all_data:
                await self._save_market_data_batch(all_data)
            return all_data
        except Exception as e:
            logger.error(f"从币安获取所有市场数据失败: {e}")
            raise
        finally:
            await client.close_connection()


class OKXMarketDataFetcher(MarketDataFetcher):
    """OKX市场数据获取器"""

    def __init__(self, config: dict[str, Any]):
        super().__init__("okx", config)

    async def fetch_market_data(self, symbols: list[str]) -> list[dict[str, Any]]:
        """从OKX获取市场数据"""
        # TODO: 实现OKX API调用
        logger.warning("OKX市场数据获取器尚未实现")
        return []

    async def fetch_all_tickers(self) -> list[dict[str, Any]]:
        """获取所有货币对的市场数据"""
        # TODO: 实现OKX API调用
        logger.warning("OKX市场数据获取器尚未实现")
        return []


class BybitMarketDataFetcher(MarketDataFetcher):
    """Bybit市场数据获取器"""

    def __init__(self, config: dict[str, Any]):
        super().__init__("bybit", config)

    async def fetch_market_data(self, symbols: list[str]) -> list[dict[str, Any]]:
        """从Bybit获取市场数据"""
        # TODO: 实现Bybit API调用
        logger.warning("Bybit市场数据获取器尚未实现")
        return []

    async def fetch_all_tickers(self) -> list[dict[str, Any]]:
        """获取所有货币对的市场数据"""
        # TODO: 实现Bybit API调用
        logger.warning("Bybit市场数据获取器尚未实现")
        return []


class MarketDataFetcherFactory:
    """市场数据获取器工厂类"""

    _fetchers: dict[str, MarketDataFetcher] = {}

    @classmethod
    def _get_exchange_config_from_db(cls, exchange_id: str) -> dict[str, Any] | None:
        """从数据库中组装交易所配置

        从分散的配置项中组装交易所配置，支持的key格式：
        - exchange.{exchange_id}.name
        - exchange.{exchange_id}.api_key
        - exchange.{exchange_id}.api_secret
        - exchange.{exchange_id}.proxy_enabled
        - exchange.{exchange_id}.proxy_url
        - exchange.{exchange_id}.proxy_username
        - exchange.{exchange_id}.proxy_password
        - exchange.{exchange_id}.is_enabled

        Args:
            exchange_id: 交易所ID

        Returns:
            Optional[Dict[str, Any]]: 交易所配置字典，如果未找到则返回None
        """
        from settings.models import SystemConfigBusiness as SystemConfig

        config = {}
        prefix = f"exchange.{exchange_id}."

        # 获取所有以 exchange.{exchange_id}. 开头的配置
        all_configs = SystemConfig.get_all()
        found = False

        for key, value in all_configs.items():
            if key.startswith(prefix):
                found = True
                # 提取配置项名称（去掉前缀）
                config_name = key[len(prefix) :]
                config[config_name] = value

        if not found:
            return None

        # 设置默认值
        config.setdefault("is_enabled", True)
        config.setdefault("name", exchange_id)

        return config

    @classmethod
    def get_fetcher(cls, exchange_id: str) -> MarketDataFetcher | None:
        """获取指定交易所的市场数据获取器

        Args:
            exchange_id: 交易所ID

        Returns:
            Optional[MarketDataFetcher]: 市场数据获取器实例，如果不支持则返回None
        """
        from settings.models import SystemConfigBusiness as SystemConfig

        # 检查缓存
        if exchange_id in cls._fetchers:
            return cls._fetchers[exchange_id]

        # 从系统配置读取交易所配置
        # 首先尝试从分散的配置项中组装
        config = cls._get_exchange_config_from_db(exchange_id)

        if not config:
            # 尝试从单个JSON配置中读取（兼容旧格式）
            config_str = SystemConfig.get(exchange_id)
            if config_str:
                try:
                    config = json.loads(config_str)
                except json.JSONDecodeError as e:
                    logger.error(f"解析交易所配置失败: {exchange_id}, error={e}")
                    return None

        if not config:
            logger.error(f"未找到交易所配置: {exchange_id}")
            return None

        # 检查交易所是否启用
        if not config.get("is_enabled", True):
            logger.warning(f"交易所已禁用: {exchange_id}")
            return None

        # 创建对应的获取器
        fetcher_class = cls._get_fetcher_class(exchange_id)
        if fetcher_class:
            fetcher = fetcher_class(config)
            cls._fetchers[exchange_id] = fetcher
            return fetcher

        logger.error(f"不支持的交易所: {exchange_id}")
        return None

    @classmethod
    def _get_fetcher_class(cls, exchange_id: str) -> type | None:
        """获取指定交易所的获取器类

        Args:
            exchange_id: 交易所ID

        Returns:
            Optional[type]: 获取器类，如果不支持则返回None
        """
        fetcher_classes = {
            "binance": BinanceMarketDataFetcher,
            "okx": OKXMarketDataFetcher,
            "bybit": BybitMarketDataFetcher,
        }
        return fetcher_classes.get(exchange_id)

    @classmethod
    def get_default_fetcher(cls) -> MarketDataFetcher | None:
        """获取默认交易所的市场数据获取器

        Returns:
            Optional[MarketDataFetcher]: 默认市场数据获取器实例
        """
        from settings.models import SystemConfigBusiness as SystemConfig

        # 从系统配置获取默认交易所
        default_exchange = SystemConfig.get("default_exchange", "binance")
        return cls.get_fetcher(default_exchange)

    @classmethod
    def clear_cache(cls):
        """清除获取器缓存"""
        cls._fetchers.clear()


# 全局工厂实例
market_data_fetcher_factory = MarketDataFetcherFactory()
