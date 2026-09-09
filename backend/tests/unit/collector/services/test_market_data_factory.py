"""collector.services.market_data_factory 单元测试。

覆盖：
- MarketDataFetcher: 初始化字段提取、代理配置（无认证/带认证）、市场数据入库（更新/新增/回滚）
- BinanceMarketDataFetcher: 客户端延迟初始化、symbol 规范化/反规范化、拉取与入库链路
- OKX/Bybit: 未实现占位返回空列表
- MarketDataFetcherFactory: 配置组装、缓存、JSON 兼容配置、禁用/不支持/默认交易所处理
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from collector.services.market_data_factory import (
    BinanceMarketDataFetcher,
    BybitMarketDataFetcher,
    MarketDataFetcher,
    MarketDataFetcherFactory,
    OKXMarketDataFetcher,
)


class _StubFetcher(MarketDataFetcher):
    """MarketDataFetcher 是抽象类，提供最小实现以测试基类的通用方法。"""

    async def fetch_market_data(self, symbols):
        return []

    async def fetch_all_tickers(self):
        return []


@pytest.fixture(autouse=True)
def _clear_factory_cache():
    """_fetchers 是类级缓存，每个测试前后清空避免用例间串扰。"""
    MarketDataFetcherFactory.clear_cache()
    yield
    MarketDataFetcherFactory.clear_cache()


TICKER = {
    "symbol": "BTCUSDT",
    "lastPrice": "42000.5",
    "priceChange": "100.0",
    "priceChangePercent": "0.24",
    "volume": "1234.5",
    "highPrice": "43000.0",
    "lowPrice": "41000.0",
}


# =================== 基类 ===================


class TestMarketDataFetcherBase:
    def test_init_extracts_config_fields(self):
        config = {
            "name": "binance",
            "proxy_enabled": True,
            "proxy_url": "http://p:1",
            "api_key": "k",
            "api_secret": "s",
        }
        fetcher = _StubFetcher("binance", config)
        assert fetcher.exchange_id == "binance"
        assert fetcher.name == "binance"
        assert fetcher.proxy_enabled is True
        assert fetcher.proxy_url == "http://p:1"
        assert fetcher.api_key == "k"
        assert fetcher.api_secret == "s"

    def test_init_defaults_when_config_missing(self):
        fetcher = _StubFetcher("binance", {})
        assert fetcher.name == "binance"
        assert fetcher.proxy_enabled is False
        assert fetcher.proxy_url == "" or fetcher.proxy_url == ""
        assert fetcher.api_key == ""

    def test_get_proxy_config_disabled_returns_none(self):
        fetcher = _StubFetcher("binance", {"proxy_enabled": False, "proxy_url": "http://p:1"})
        assert fetcher._get_proxy_config() is None

    def test_get_proxy_config_enabled_without_url_returns_none(self):
        fetcher = _StubFetcher("binance", {"proxy_enabled": True})
        assert fetcher._get_proxy_config() is None

    def test_get_proxy_config_basic(self):
        fetcher = _StubFetcher("binance", {"proxy_enabled": True, "proxy_url": "http://proxy:8080"})
        cfg = fetcher._get_proxy_config()
        assert cfg == {"http": "http://proxy:8080", "https": "http://proxy:8080"}

    def test_get_proxy_config_with_auth_embeds_credentials(self):
        fetcher = _StubFetcher(
            "binance",
            {"proxy_enabled": True, "proxy_url": "http://proxy:8080", "proxy_username": "u", "proxy_password": "p"},
        )
        cfg = fetcher._get_proxy_config()
        assert cfg["http"] == "http://u:p@proxy:8080"
        assert cfg["https"] == "http://u:p@proxy:8080"


# =================== 入库 ===================


class TestSaveMarketDataToDb:
    async def test_update_existing_record(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = MagicMock(symbol="BTC/USDT")
        with patch("collector.services.market_data_factory.get_db", return_value=iter([db])) as m_get_db:
            fetcher = _StubFetcher("binance", {})
            data = {
                "symbol": "BTC/USDT",
                "price": "42000.5",
                "price_change_24h": "100",
                "price_change_percent_24h": "0.24",
                "volume_24h": "1234.5",
                "high_24h": "43000",
                "low_24h": "41000",
            }
            await fetcher._save_market_data_to_db(data)
        m_get_db.assert_called_once()
        record = db.query.return_value.filter.return_value.first.return_value
        assert str(record.price) == "42000.5"
        assert str(record.volume_24h) == "1234.5"
        # 已存在的记录应更新最后更新时间，而不是新增
        assert record.last_update is not None
        db.add.assert_not_called()
        db.commit.assert_called_once()

    async def test_insert_new_record(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        with (
            patch("collector.services.market_data_factory.get_db", return_value=iter([db])),
            patch(
                # 实例化 MarketData 会触发 SQLAlchemy mapper 配置，测试环境存在
                # Worker.Strategy relationship 解析失败，因此直接替换模型类
                "collector.services.market_data_factory.MarketData",
                return_value=MagicMock(),
            ),
        ):
            fetcher = _StubFetcher("binance", {})
            await fetcher._save_market_data_to_db({"symbol": "BTC/USDT", "price": "1.0", "high_24h": "2.0"})
        db.add.assert_called_once()
        db.commit.assert_called_once()

    async def test_exception_rolls_back(self):
        db = MagicMock()
        db.query.side_effect = RuntimeError("boom")
        with patch("collector.services.market_data_factory.get_db", return_value=iter([db])):
            await _StubFetcher("binance", {})._save_market_data_to_db({"symbol": "X"})
        db.rollback.assert_called_once()
        db.commit.assert_not_called()
        db.close.assert_called_once()


# =================== Binance 客户端 ===================


class TestBinanceClient:
    def test_get_client_returns_cached(self):
        fetcher = BinanceMarketDataFetcher({})
        fetcher._client = MagicMock()
        with patch("binance.client.Client") as m:
            assert fetcher._get_client() is fetcher._client
        m.assert_not_called()

    def test_get_client_with_config_proxy(self):
        fetcher = BinanceMarketDataFetcher(
            {"api_key": "k", "api_secret": "s", "proxy_enabled": True, "proxy_url": "http://p:8080"}
        )
        with patch("binance.client.Client") as m:
            fetcher._get_client()
        m.assert_called_once_with("k", "s", {"proxies": {"http": "http://p:8080", "https": "http://p:8080"}})

    def test_get_client_with_env_proxy(self):
        fetcher = BinanceMarketDataFetcher({"api_key": "k", "api_secret": "s"})
        with (
            patch.dict("os.environ", {"https_proxy": "http://env:8888"}, clear=False),
            patch("binance.client.Client") as m,
        ):
            fetcher._get_client()
        m.assert_called_once_with("k", "s", {"proxies": {"http": "http://env:8888", "https": "http://env:8888"}})

    def test_get_client_without_proxy(self):
        fetcher = BinanceMarketDataFetcher({"api_key": "k", "api_secret": "s"})
        with patch("binance.client.Client") as m:
            fetcher._get_client()
        m.assert_called_once_with("k", "s")

    def test_normalize_symbol(self):
        assert BinanceMarketDataFetcher({})._normalize_symbol("BTC/USDT") == "BTCUSDT"

    def test_denormalize_known_quote(self):
        assert BinanceMarketDataFetcher({})._denormalize_symbol("BTCUSDT") == "BTC/USDT"

    def test_denormalize_unknown_quote_unchanged(self):
        assert BinanceMarketDataFetcher({})._denormalize_symbol("SOMETHINGSTRANGE") == "SOMETHINGSTRANGE"


# =================== Binance 拉取 ===================


class TestBinanceFetch:
    async def test_fetch_market_data_maps_and_saves(self):
        fetcher = BinanceMarketDataFetcher({})
        client = MagicMock()
        client.get_ticker.return_value = TICKER
        with (
            patch.object(fetcher, "_get_client", return_value=client),
            patch.object(fetcher, "_save_market_data_to_db", new=AsyncMock()) as m_save,
        ):
            data = await fetcher.fetch_market_data(["BTC/USDT"])
        assert len(data) == 1
        assert data[0]["symbol"] == "BTC/USDT"
        assert data[0]["price"] == 42000.5
        assert data[0]["high_24h"] == 43000.0
        m_save.assert_called_once()

    async def test_fetch_market_data_continues_on_symbol_error(self):
        fetcher = BinanceMarketDataFetcher({})
        client = MagicMock()
        client.get_ticker.side_effect = [TICKER, RuntimeError("bad symbol")]
        with (
            patch.object(fetcher, "_get_client", return_value=client),
            patch.object(fetcher, "_save_market_data_to_db", new=AsyncMock()),
        ):
            data = await fetcher.fetch_market_data(["BTC/USDT", "ETH/USDT"])
        assert len(data) == 1
        assert client.get_ticker.call_count == 2

    async def test_fetch_all_tickers(self):
        fetcher = BinanceMarketDataFetcher({})
        client = MagicMock()
        client.get_ticker.return_value = [TICKER]
        with (
            patch.object(fetcher, "_get_client", return_value=client),
            patch.object(fetcher, "_save_market_data_to_db", new=AsyncMock()) as m_save,
        ):
            data = await fetcher.fetch_all_tickers()
        assert len(data) == 1
        assert data[0]["symbol"] == "BTC/USDT"
        m_save.assert_called_once()

    async def test_fetch_market_data_propagates_client_error(self):
        # 客户端初始化失败属于外层错误，直接向上抛出而非静默跳过
        fetcher = BinanceMarketDataFetcher({})
        with patch.object(fetcher, "_get_client", side_effect=RuntimeError("conn failed")):
            with pytest.raises(RuntimeError):
                await fetcher.fetch_market_data(["BTC/USDT"])

    async def test_fetch_all_tickers_propagates_client_error(self):
        fetcher = BinanceMarketDataFetcher({})
        client = MagicMock()
        client.get_ticker.side_effect = RuntimeError("api down")
        with patch.object(fetcher, "_get_client", return_value=client):
            with pytest.raises(RuntimeError):
                await fetcher.fetch_all_tickers()


# =================== 未实现交易所 ===================


class TestUnimplementedFetchers:
    async def test_okx_returns_empty(self):
        fetcher = OKXMarketDataFetcher({})
        assert await fetcher.fetch_market_data(["BTC/USDT"]) == []
        assert await fetcher.fetch_all_tickers() == []

    async def test_bybit_returns_empty(self):
        fetcher = BybitMarketDataFetcher({})
        assert await fetcher.fetch_market_data(["BTC/USDT"]) == []
        assert await fetcher.fetch_all_tickers() == []


# =================== 工厂 ===================


class TestMarketDataFetcherFactory:
    def test_load_config_from_db(self):
        with patch(
            "settings.models.SystemConfigBusiness.get_all",
            return_value={
                "exchange.binance.api_key": "k",
                "exchange.binance.name": "Binance",
                "exchange.binance.proxy_enabled": "1",
            },
        ):
            cfg = MarketDataFetcherFactory._get_exchange_config_from_db("binance")
        assert cfg["api_key"] == "k"
        assert cfg["name"] == "Binance"
        # 缺失的键走默认值
        assert cfg["is_enabled"] is True

    def test_load_config_not_found_returns_none(self):
        with patch("settings.models.SystemConfigBusiness.get_all", return_value={}):
            assert MarketDataFetcherFactory._get_exchange_config_from_db("binance") is None

    def test_get_fetcher_uses_cache(self):
        stub = MagicMock()
        MarketDataFetcherFactory._fetchers["binance"] = stub
        with patch.object(MarketDataFetcherFactory, "_get_exchange_config_from_db", return_value={}) as m:
            assert MarketDataFetcherFactory.get_fetcher("binance") is stub
        m.assert_not_called()

    def test_get_fetcher_from_scattered_config(self):
        cfg = {"api_key": "k", "name": "Binance", "is_enabled": True}
        with patch.object(MarketDataFetcherFactory, "_get_exchange_config_from_db", return_value=cfg):
            fetcher = MarketDataFetcherFactory.get_fetcher("binance")
        assert isinstance(fetcher, BinanceMarketDataFetcher)

    def test_get_fetcher_from_json_compat_config(self):
        cfg_str = json.dumps({"api_key": "k", "is_enabled": True, "name": "Binance"})
        with (
            patch.object(MarketDataFetcherFactory, "_get_exchange_config_from_db", return_value=None),
            patch("settings.models.SystemConfigBusiness.get", return_value=cfg_str),
        ):
            fetcher = MarketDataFetcherFactory.get_fetcher("binance")
        assert isinstance(fetcher, BinanceMarketDataFetcher)

    def test_get_fetcher_invalid_json_returns_none(self):
        # get_fetcher 内部捕获 JSONDecodeError 并返回 None，不向外抛出
        with (
            patch.object(MarketDataFetcherFactory, "_get_exchange_config_from_db", return_value=None),
            patch("settings.models.SystemConfigBusiness.get", return_value="{broken"),
        ):
            assert MarketDataFetcherFactory.get_fetcher("binance") is None

    def test_get_fetcher_not_found_returns_none(self):
        with (
            patch.object(MarketDataFetcherFactory, "_get_exchange_config_from_db", return_value=None),
            patch("settings.models.SystemConfigBusiness.get", return_value=None),
        ):
            assert MarketDataFetcherFactory.get_fetcher("binance") is None

    def test_get_fetcher_disabled_exchange_returns_none(self):
        cfg = {"is_enabled": False, "name": "Binance"}
        with patch.object(MarketDataFetcherFactory, "_get_exchange_config_from_db", return_value=cfg):
            assert MarketDataFetcherFactory.get_fetcher("binance") is None

    def test_get_fetcher_unsupported_returns_none(self):
        with patch.object(MarketDataFetcherFactory, "_get_exchange_config_from_db", return_value={"name": "x"}):
            assert MarketDataFetcherFactory.get_fetcher("unknown_exchange") is None

    def test_get_default_fetcher(self):
        with (
            patch.object(MarketDataFetcherFactory, "_get_exchange_config_from_db", return_value={"name": "Binance"}),
            patch("settings.models.SystemConfigBusiness.get", return_value="binance"),
        ):
            fetcher = MarketDataFetcherFactory.get_default_fetcher()
        assert isinstance(fetcher, BinanceMarketDataFetcher)

    def test_get_default_fetcher_without_config_returns_none(self):
        # 无任何配置时 default_exchange 落入 get_fetcher 的未找到分支
        with (
            patch.object(MarketDataFetcherFactory, "_get_exchange_config_from_db", return_value=None),
            patch("settings.models.SystemConfigBusiness.get", return_value=None),
        ):
            assert MarketDataFetcherFactory.get_default_fetcher() is None

    def test_get_fetcher_class_mapping(self):
        assert MarketDataFetcherFactory._get_fetcher_class("binance") is BinanceMarketDataFetcher
        assert MarketDataFetcherFactory._get_fetcher_class("okx") is OKXMarketDataFetcher
        assert MarketDataFetcherFactory._get_fetcher_class("bybit") is BybitMarketDataFetcher
        assert MarketDataFetcherFactory._get_fetcher_class("unknown") is None

    def test_clear_cache(self):
        MarketDataFetcherFactory._fetchers["binance"] = MagicMock()
        MarketDataFetcherFactory.clear_cache()
        assert MarketDataFetcherFactory._fetchers == {}
