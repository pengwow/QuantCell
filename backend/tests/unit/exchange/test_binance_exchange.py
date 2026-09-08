"""
BinanceExchange 单元测试

覆盖 exchange/binance/exchange.py 的纯逻辑部分，全部通过 patch 模块级 ccxt 目标绕开网络：

- __init__ 使用模块级 ccxt.binance 构造（apiKey/secret/proxies 配置）
- _configure_testnet 的 URL 改写（spot / future 两种路径 + api 字典重写）
- format_candle 静态方法纯断言
- symbols 懒加载 property 过滤含冒号的合约
- connect / health_check / check_status 的成功与失败分支
- download_data 在 fetch_ohlcv 抛错时返回 []

作者: QuantCell Team
"""

from unittest import mock

import pytest

from exchange.binance.exchange import BinanceExchange


def _base_urls() -> dict:
    """构造一份接近 ccxt binance 的默认 urls 结构"""
    return {
        "www": "https://www.binance.com",
        "api": "https://api.binance.com/api/v3",
        "public": "https://api.binance.com/api/v3",
        "private": "https://api.binance.com/api/v3",
        "fapi": "https://fapi.binance.com",
        "fapiPublic": "https://fapi.binance.com/fapi/v1",
        "fapiPrivate": "https://fapi.binance.com/fapi/v1",
        "dapi": "https://dapi.binance.com",
    }


def _futures_api_dict_urls() -> dict:
    """futures 模式下 api 端点为 dict 的 urls 结构（供 api 字典重写分支使用）"""
    return {
        "www": "https://www.binance.com",
        "api": {
            "public": "https://api.binance.com/api/v3",
            "private": "https://api.binance.com/api/v3",
            "sapi": "https://api.binance.com/sapi/v1",
            "fapiPublic": "https://fapi.binance.com/fapi/v1",
            "fapiPrivate": "https://fapi.binance.com/fapi/v1",
            "dapiPublic": "https://dapi.binance.com/dapi/v1",
        },
        "fapi": "https://fapi.binance.com",
        "fapiPublic": "https://fapi.binance.com/fapi/v1",
        "fapiPrivate": "https://fapi.binance.com/fapi/v1",
        "dapi": "https://dapi.binance.com",
    }


def _make_client(exchange: mock.MagicMock, **kwargs) -> BinanceExchange:
    """通过 patch 模块级 ccxt.binance 构造 BinanceExchange，避免真实网络请求"""
    kwargs.setdefault("exchange_name", "binance")
    with mock.patch("exchange.binance.exchange.ccxt.binance", return_value=exchange):
        return BinanceExchange(**kwargs)


def _sample_candle() -> list:
    """构造一条 12 字段的 BTC 1h K 线"""
    return [
        1704067200000,  # open_time
        40000.0,  # open
        41000.0,  # high
        39000.0,  # low
        40500.0,  # close
        1000.0,  # volume
        1704067200000 + 3599999,  # close_time
        50000.0,  # quote_volume
        100,  # count
        500.0,  # taker_buy_volume
        250.0,  # taker_buy_quote_volume
        0,  # ignore
    ]


class TestInit:
    """测试 __init__ 的 ccxt 构造与配置注入"""

    def test_init_ccxt_constructor_with_credentials_and_proxy(self):
        exchange = mock.MagicMock()
        exchange.urls = _base_urls()
        with mock.patch("exchange.binance.exchange.ccxt.binance", return_value=exchange) as mock_ccxt_cls:
            BinanceExchange(
                exchange_name="binance",
                api_key="my-api-key",
                secret_key="my-secret",
                trading_mode="spot",
                proxy_url="http://127.0.0.1:8080",
            )

        config = mock_ccxt_cls.call_args.args[0]
        assert config["enableRateLimit"] is True
        assert config["options"] == {"defaultType": "spot"}
        assert config["apiKey"] == "my-api-key"
        assert config["secret"] == "my-secret"
        assert config["proxies"] == {"http": "http://127.0.0.1:8080", "https": "http://127.0.0.1:8080"}

    def test_init_without_credentials_omits_keys(self):
        """未提供凭据时，config 中不包含 apiKey/secret/proxies"""
        exchange = mock.MagicMock()
        exchange.urls = _base_urls()
        with mock.patch("exchange.binance.exchange.ccxt.binance", return_value=exchange) as mock_ccxt_cls:
            BinanceExchange()

        config = mock_ccxt_cls.call_args.args[0]
        assert "apiKey" not in config
        assert "secret" not in config
        assert "proxies" not in config

    def test_init_parses_ohlcv_and_default_type(self):
        """构造后 parse_ohlcv 被替换为自定义方法，trading_mode/_symbols 初始化正确"""
        exchange = mock.MagicMock()
        exchange.urls = _base_urls()
        client = _make_client(exchange)

        # 通过实例 __dict__ 读取属性，避免 MagicMock 属性访问自动生成 mock child
        assert client.exchange is exchange
        stored = exchange.__dict__["parse_ohlcv"]
        assert stored.__func__ is BinanceExchange.parse_ohlcv_custom
        assert stored.__self__ is client
        assert client.trading_mode == "spot"
        assert client._symbols is None
        assert client.candle_names[0] == "open_time"


class TestConfigureTestnet:
    """测试 _configure_testnet 的 URL 改写"""

    def test_configure_testnet_spot_rewrites_urls(self):
        # 初始化时 testnet=True 直接触发 URL 改写
        exchange = mock.MagicMock()
        exchange.urls = _base_urls()
        _make_client(exchange, testnet=True, trading_mode="spot")

        urls = exchange.urls
        assert urls["www"] == "https://testnet.binance.vision"
        assert urls["api"] == "https://testnet.binance.vision/api/v3"
        assert urls["public"] == "https://testnet.binance.vision/api/v3"
        assert urls["private"] == "https://testnet.binance.vision/api/v3"

    def test_configure_testnet_future_rewrites_urls(self):
        exchange = mock.MagicMock()
        exchange.urls = _base_urls()
        _make_client(exchange, testnet=True, trading_mode="future")

        urls = exchange.urls
        base = "https://testnet.binancefuture.com"
        assert urls["www"] == base
        assert urls["fapi"] == base + "/fapi/v1"
        assert urls["fapiPublic"] == base + "/fapi/v1"
        assert urls["fapiPrivate"] == base + "/fapi/v1"
        assert urls["public"] == base + "/fapi/v1/ticker/price"
        assert urls["private"] == base + "/fapi/v1"

    def test_configure_testnet_futures_alias_works(self):
        exchange = mock.MagicMock()
        exchange.urls = _base_urls()
        _make_client(exchange, testnet=True, trading_mode="futures")

        assert exchange.urls["www"] == "https://testnet.binancefuture.com"

    def test_configure_testnet_future_api_dict_rewrites(self):
        """api 为 dict 时，fapi/dapi/api.binance.com 域名统一替换到 testnet"""
        exchange = mock.MagicMock()
        exchange.urls = _futures_api_dict_urls()
        _make_client(exchange, testnet=True, trading_mode="future")

        api = exchange.urls["api"]
        assert api["public"] == "https://testnet.binancefuture.com/fapi/v1"
        assert api["private"] == "https://testnet.binancefuture.com/fapi/v1"
        assert api["sapi"] == "https://testnet.binancefuture.com/sapi/v1"
        assert api["fapiPublic"] == "https://testnet.binancefuture.com/fapi/v1"
        assert api["fapiPrivate"] == "https://testnet.binancefuture.com/fapi/v1"
        assert api["dapiPublic"] == "https://testnet.binancefuture.com/dapi/v1"

    def test_configure_testnet_unknown_mode_leaves_urls_untouched(self):
        exchange = mock.MagicMock()
        exchange.urls = _base_urls()
        _make_client(exchange, testnet=True, trading_mode="margin")

        assert exchange.urls == _base_urls()


class TestFormatCandle:
    """测试 format_candle 静态方法"""

    def test_format_candle_maps_all_fields(self):
        candle = _sample_candle()
        result = BinanceExchange.format_candle(candle)

        assert result["open_time"] == 1704067200000
        assert result["open"] == 40000.0
        assert result["high"] == 41000.0
        assert result["low"] == 39000.0
        assert result["close"] == 40500.0
        assert result["volume"] == 1000.0
        assert result["close_time"] == 1704070799999
        assert result["quote_volume"] == 50000.0
        assert result["count"] == 100
        assert result["taker_buy_volume"] == 500.0
        assert result["taker_buy_quote_volume"] == 250.0
        assert result["ignore"] == 0

    def test_format_candle_is_staticmethod(self):
        assert isinstance(BinanceExchange.__dict__["format_candle"], staticmethod)


class TestSymbols:
    """测试 symbols property 的过滤与懒加载"""

    def test_symbols_filters_contract_symbols(self):
        exchange = mock.MagicMock()
        exchange.urls = _base_urls()
        exchange.symbols = ["BTCUSDT", "ETHUSDT", "BTCUSDT:USDT", "SOLUSDT:USDT", "BNBUSDT"]
        client = _make_client(exchange)

        assert client.symbols == ["BTCUSDT", "ETHUSDT", "BNBUSDT"]

    def test_symbols_is_lazy_and_cached(self):
        exchange = mock.MagicMock()
        exchange.urls = _base_urls()
        exchange.symbols = ["BTCUSDT"]
        client = _make_client(exchange)

        first = client.symbols
        # 修改底层数据后再次访问，应仍返回缓存结果（证明只读取了一次并缓存）
        exchange.symbols = ["BTCUSDT", "ETHUSDT"]
        assert client.symbols == first
        assert client.symbols == ["BTCUSDT"]


class TestConnection:
    """测试 connect / health_check / check_status"""

    def test_connect_success(self):
        exchange = mock.MagicMock()
        exchange.urls = _base_urls()
        client = _make_client(exchange)

        assert client.connect() is True
        assert client._connected is True
        exchange.load_markets.assert_called_once()

    def test_connect_failure_sets_connected_false(self):
        exchange = mock.MagicMock()
        exchange.urls = _base_urls()
        exchange.load_markets.side_effect = RuntimeError("network down")
        client = _make_client(exchange)

        assert client.connect() is False
        assert client._connected is False

    def test_health_check_success(self):
        exchange = mock.MagicMock()
        exchange.urls = _base_urls()
        exchange.fetch_time.return_value = 1700000000000
        client = _make_client(exchange)

        assert client.health_check() is True

    def test_health_check_failure_returns_false(self):
        exchange = mock.MagicMock()
        exchange.urls = _base_urls()
        exchange.fetch_time.side_effect = RuntimeError("timeout")
        client = _make_client(exchange)

        assert client.health_check() is False

    def test_check_status_ok(self):
        exchange = mock.MagicMock()
        exchange.urls = _base_urls()
        exchange.fetch_status.return_value = {"status": "ok"}
        client = _make_client(exchange)

        assert client.check_status() is True

    def test_check_status_not_ok(self):
        exchange = mock.MagicMock()
        exchange.urls = _base_urls()
        exchange.fetch_status.return_value = {"status": "maintenance"}
        client = _make_client(exchange)

        assert client.check_status() is False

    def test_check_status_falls_back_to_health_check(self):
        exchange = mock.MagicMock()
        exchange.urls = _base_urls()
        exchange.fetch_status.side_effect = RuntimeError("unknown")
        exchange.fetch_time.return_value = 1700000000000
        client = _make_client(exchange)

        assert client.check_status() is True

    def test_check_status_fallback_failure_returns_false(self):
        exchange = mock.MagicMock()
        exchange.urls = _base_urls()
        exchange.fetch_status.side_effect = RuntimeError("unknown")
        exchange.fetch_time.side_effect = RuntimeError("timeout")
        client = _make_client(exchange)

        assert client.check_status() is False


class TestDownloadData:
    """测试 download_data / load_data / get_balance"""

    def test_download_data_success_formats_candles(self):
        candle = _sample_candle()
        exchange = mock.MagicMock()
        exchange.urls = _base_urls()
        exchange.fetch_ohlcv.return_value = [candle, candle]
        client = _make_client(exchange)

        result = client.download_data("BTCUSDT", "1h")
        assert len(result) == 2
        assert result[0] == BinanceExchange.format_candle(candle)

    def test_download_data_forwards_ohlcv_params(self):
        exchange = mock.MagicMock()
        exchange.urls = _base_urls()
        exchange.fetch_ohlcv.return_value = []
        client = _make_client(exchange)

        client.download_data("BTCUSDT", "1h", start_time=1700000000000, end_time=1700003600000, limit=100)

        exchange.fetch_ohlcv.assert_called_once_with(
            symbol="BTCUSDT",
            timeframe="1h",
            since=1700000000000,
            limit=100,
        )

    def test_download_data_failure_returns_empty_list(self):
        exchange = mock.MagicMock()
        exchange.urls = _base_urls()
        exchange.fetch_ohlcv.side_effect = RuntimeError("rate limited")
        client = _make_client(exchange)

        assert client.download_data("BTCUSDT", "1h") == []

    def test_download_data_empty_returns_empty_list(self):
        exchange = mock.MagicMock()
        exchange.urls = _base_urls()
        exchange.fetch_ohlcv.return_value = None
        client = _make_client(exchange)

        assert client.download_data("BTCUSDT", "1h") == []

    def test_load_data_delegates_to_download_data(self):
        exchange = mock.MagicMock()
        exchange.urls = _base_urls()
        client = _make_client(exchange)
        fake_candles = [{"open_time": 1}]
        client.download_data = mock.MagicMock(return_value=fake_candles)

        result = client.load_data("BTCUSDT", "1h", 1700000000000, 1700003600000)
        assert result == fake_candles
        client.download_data.assert_called_once_with("BTCUSDT", "1h", 1700000000000, 1700003600000)

    def test_get_balance_success(self):
        exchange = mock.MagicMock()
        exchange.urls = _base_urls()
        exchange.fetch_balance.return_value = {"total": {"BTC": 1.0}}
        client = _make_client(exchange)

        assert client.get_balance() == {"total": {"BTC": 1.0}}

    def test_get_balance_failure_returns_empty_dict(self):
        exchange = mock.MagicMock()
        exchange.urls = _base_urls()
        exchange.fetch_balance.side_effect = RuntimeError("auth failed")
        client = _make_client(exchange)

        assert client.get_balance() == {}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
