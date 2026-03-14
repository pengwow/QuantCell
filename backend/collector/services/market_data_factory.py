"""市场数据工厂模块

基于工厂模式实现多交易所市场数据获取的统一接口
支持从系统配置读取代理信息
"""
import json
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from datetime import datetime
from decimal import Decimal
from utils.logger import get_logger, LogType

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)
from collector.db.database import get_db
from collector.db.models import MarketData
from settings.models import SystemConfigBusiness as SystemConfig


class MarketDataFetcher(ABC):
    """市场数据获取器抽象基类

    定义了获取市场数据的统一接口，不同交易所的获取器需要实现此接口
    """

    def __init__(self, exchange_id: str, config: Dict[str, Any]):
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
    async def fetch_market_data(self, symbols: List[str]) -> List[Dict[str, Any]]:
        """获取市场数据

        Args:
            symbols: 货币对列表

        Returns:
            List[Dict]: 市场数据列表
        """
        pass

    @abstractmethod
    async def fetch_all_tickers(self) -> List[Dict[str, Any]]:
        """获取所有货币对的市场数据

        Returns:
            List[Dict]: 市场数据列表
        """
        pass

    def _get_proxy_config(self) -> Optional[Dict[str, str]]:
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
                (parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment)
            )
            proxy_config = {
                "http": proxy_url_with_auth,
                "https": proxy_url_with_auth,
            }

        return proxy_config

    async def _save_market_data_to_db(self, data: Dict[str, Any]):
        """保存市场数据到数据库

        Args:
            data: 市场数据字典
        """
        db = next(get_db())
        try:
            record = db.query(MarketData).filter(
                MarketData.symbol == data["symbol"],
                MarketData.exchange == self.exchange_id
            ).first()

            if record:
                # 更新
                record.price = Decimal(str(data["price"])) if data.get("price") else None
                record.price_change_24h = Decimal(str(data["price_change_24h"])) if data.get("price_change_24h") else None
                record.price_change_percent_24h = Decimal(str(data["price_change_percent_24h"])) if data.get("price_change_percent_24h") else None
                record.volume_24h = Decimal(str(data["volume_24h"])) if data.get("volume_24h") else None
                record.high_24h = Decimal(str(data["high_24h"])) if data.get("high_24h") else None
                record.low_24h = Decimal(str(data["low_24h"])) if data.get("low_24h") else None
                record.last_update = datetime.utcnow()
            else:
                # 新建
                new_record = MarketData(
                    symbol=data["symbol"],
                    exchange=self.exchange_id,
                    price=Decimal(str(data["price"])) if data.get("price") else None,
                    price_change_24h=Decimal(str(data["price_change_24h"])) if data.get("price_change_24h") else None,
                    price_change_percent_24h=Decimal(str(data["price_change_percent_24h"])) if data.get("price_change_percent_24h") else None,
                    volume_24h=Decimal(str(data["volume_24h"])) if data.get("volume_24h") else None,
                    high_24h=Decimal(str(data["high_24h"])) if data.get("high_24h") else None,
                    low_24h=Decimal(str(data["low_24h"])) if data.get("low_24h") else None,
                    last_update=datetime.utcnow()
                )
                db.add(new_record)

            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"保存市场数据到数据库失败: {e}")
        finally:
            db.close()


class BinanceMarketDataFetcher(MarketDataFetcher):
    """币安市场数据获取器"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__("binance", config)
        self._client = None

    def _get_client(self):
        """获取币安客户端（延迟初始化）"""
        if self._client is None:
            from binance.client import Client

            proxies = self._get_proxy_config()
            logger.info(f"初始化币安客户端，代理: {proxies is not None}")

            if proxies:
                self._client = Client(self.api_key, self.api_secret, {"proxies": proxies})
            else:
                self._client = Client(self.api_key, self.api_secret)

        return self._client

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
        quote_currencies = ["USDT", "BTC", "ETH", "BNB", "USDC", "TUSD", "BUSD", "DAI", "PAX", "USDS"]

        for quote in quote_currencies:
            if symbol.endswith(quote):
                base = symbol[:-len(quote)]
                return f"{base}/{quote}"

        # 如果无法识别，直接返回原值
        return symbol

    async def fetch_market_data(self, symbols: List[str]) -> List[Dict[str, Any]]:
        """从币安获取市场数据"""
        try:
            client = self._get_client()
            all_data = []

            # 币安 API 限制：每次最多请求 100 个 symbol
            # 但使用 symbols 参数时，需要传递 JSON 数组字符串
            # 为了避免复杂性，我们逐个获取
            for symbol in symbols:
                logger.info(f"从币安获取{symbol}的市场数据")

                # 转换symbol格式：BTC/USDT -> BTCUSDT
                normalized_symbol = self._normalize_symbol(symbol)

                try:
                    ticker = client.get_ticker(symbol=normalized_symbol)

                    # 转换symbol格式：BTCUSDT -> BTC/USDT
                    denormalized_symbol = self._denormalize_symbol(ticker["symbol"])
                    data = {
                        "symbol": denormalized_symbol,
                        "price": float(ticker["lastPrice"]),
                        "price_change_24h": float(ticker["priceChange"]),
                        "price_change_percent_24h": float(ticker["priceChangePercent"]),
                        "volume_24h": float(ticker["volume"]),
                        "high_24h": float(ticker["highPrice"]),
                        "low_24h": float(ticker["lowPrice"]),
                        "last_update": datetime.utcnow().isoformat()
                    }
                    all_data.append(data)
                    await self._save_market_data_to_db(data)
                except Exception as e:
                    logger.warning(f"获取{symbol}的市场数据失败: {e}")
                    continue

            return all_data

        except Exception as e:
            logger.error(f"从币安获取市场数据失败: {e}")
            raise

    async def fetch_all_tickers(self) -> List[Dict[str, Any]]:
        """获取所有货币对的市场数据"""
        try:
            client = self._get_client()
            tickers = client.get_ticker()

            all_data = []
            for ticker in tickers:
                # 转换symbol格式：BTCUSDT -> BTC/USDT
                normalized_symbol = self._denormalize_symbol(ticker["symbol"])
                data = {
                    "symbol": normalized_symbol,
                    "price": float(ticker["lastPrice"]),
                    "price_change_24h": float(ticker["priceChange"]),
                    "price_change_percent_24h": float(ticker["priceChangePercent"]),
                    "volume_24h": float(ticker["volume"]),
                    "high_24h": float(ticker["highPrice"]),
                    "low_24h": float(ticker["lowPrice"]),
                    "last_update": datetime.utcnow().isoformat()
                }
                all_data.append(data)
                await self._save_market_data_to_db(data)

            return all_data

        except Exception as e:
            logger.error(f"从币安获取所有市场数据失败: {e}")
            raise


class OKXMarketDataFetcher(MarketDataFetcher):
    """OKX市场数据获取器"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__("okx", config)

    async def fetch_market_data(self, symbols: List[str]) -> List[Dict[str, Any]]:
        """从OKX获取市场数据"""
        # TODO: 实现OKX API调用
        logger.warning("OKX市场数据获取器尚未实现")
        return []

    async def fetch_all_tickers(self) -> List[Dict[str, Any]]:
        """获取所有货币对的市场数据"""
        # TODO: 实现OKX API调用
        logger.warning("OKX市场数据获取器尚未实现")
        return []


class BybitMarketDataFetcher(MarketDataFetcher):
    """Bybit市场数据获取器"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__("bybit", config)

    async def fetch_market_data(self, symbols: List[str]) -> List[Dict[str, Any]]:
        """从Bybit获取市场数据"""
        # TODO: 实现Bybit API调用
        logger.warning("Bybit市场数据获取器尚未实现")
        return []

    async def fetch_all_tickers(self) -> List[Dict[str, Any]]:
        """获取所有货币对的市场数据"""
        # TODO: 实现Bybit API调用
        logger.warning("Bybit市场数据获取器尚未实现")
        return []


class MarketDataFetcherFactory:
    """市场数据获取器工厂类"""

    _fetchers: Dict[str, MarketDataFetcher] = {}

    @classmethod
    def _get_exchange_config_from_db(cls, exchange_id: str) -> Optional[Dict[str, Any]]:
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
        config = {}
        prefix = f"exchange.{exchange_id}."
        
        # 获取所有以 exchange.{exchange_id}. 开头的配置
        all_configs = SystemConfig.get_all()
        found = False
        
        for key, value in all_configs.items():
            if key.startswith(prefix):
                found = True
                # 提取配置项名称（去掉前缀）
                config_name = key[len(prefix):]
                config[config_name] = value
        
        if not found:
            return None
            
        # 设置默认值
        config.setdefault("is_enabled", True)
        config.setdefault("name", exchange_id)
        
        return config

    @classmethod
    def get_fetcher(cls, exchange_id: str) -> Optional[MarketDataFetcher]:
        """获取指定交易所的市场数据获取器

        Args:
            exchange_id: 交易所ID

        Returns:
            Optional[MarketDataFetcher]: 市场数据获取器实例，如果不支持则返回None
        """
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
    def _get_fetcher_class(cls, exchange_id: str) -> Optional[type]:
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
    def get_default_fetcher(cls) -> Optional[MarketDataFetcher]:
        """获取默认交易所的市场数据获取器

        Returns:
            Optional[MarketDataFetcher]: 默认市场数据获取器实例
        """
        # 从系统配置获取默认交易所
        default_exchange = SystemConfig.get("default_exchange", "binance")
        return cls.get_fetcher(default_exchange)

    @classmethod
    def clear_cache(cls):
        """清除获取器缓存"""
        cls._fetchers.clear()


# 全局工厂实例
market_data_fetcher_factory = MarketDataFetcherFactory()
