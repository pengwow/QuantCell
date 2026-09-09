"""
Exchange 核心模块单元测试

覆盖 exchange/decorators.py、exchange/axon_exchange_adapter.py、
exchange/connection.py 三者的关键逻辑：

- api_retry：重试成功 / retry_after 分支 / 指数退避延迟序列 / 最终抛出
- require_connected：未连接抛 ConnectionError
- require_feature：按 _exchange_features 匹配，不支持的抛 NotImplementedFeatureError
- rate_limit：超限时阻塞
- ExchangeAdapter：AXON_AVAILABLE 门控的 RuntimeError / 非法 exchange_id 的 ValueError
- ExchangeAdapterProxy：axon 不可用时的空实现默认返回值
- connection._create_exchange_instance：内部工厂函数（patch 内部 import）

运行环境不依赖 pytest-asyncio，全部为标准 pytest + unittest.mock。

作者: QuantCell Team
"""

from unittest import mock

import pytest

import exchange.axon_exchange_adapter as adapter_mod
import exchange.connection as connection_mod
from exchange.axon_exchange_adapter import ExchangeAdapter, ExchangeAdapterProxy
from exchange.decorators import api_retry, rate_limit, require_connected, require_feature
from exchange.exceptions import ConnectionError, NotImplementedFeatureError, RateLimitError
from exchange.types import ConnectionStatus

# ---- 供装饰器测试使用的桩类 ----


class _NoFeaturesExchange:
    """没有 _exchange_features 属性的桩"""

    exchange_name = "no-features"

    @require_feature("spot_trading")
    def trade(self):
        return "no-features"


class _StubExchangeFeatures:
    """测试 require_feature 时用于匹配 _exchange_features 的桩"""

    exchange_name = "stub"

    _exchange_features = {"spot_trading": True}

    @require_feature("spot_trading")
    def trade_spot(self):
        return "spot-ok"

    @require_feature("sub_account")
    def list_sub_accounts(self):
        return "sub-ok"


class _StubConnected:
    def __init__(self, connected: bool):
        self._connected = connected
        self.exchange_name = "stub"

    @require_connected
    def ping(self):
        return "pong"


class TestApiRetry:
    """测试 api_retry 重试装饰器"""

    def test_success_after_transient_failures(self):
        """连续抛 RateLimitError 后再成功，返回最终结果并只重试必要次数"""
        attempts = {"count": 0}

        @api_retry(max_retries=3, delay=0.01, backoff=2.0)
        def flaky():
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise RateLimitError("rate limited")
            return "ok"

        with mock.patch("exchange.decorators.time.sleep"):
            assert flaky() == "ok"
        assert attempts["count"] == 3

    def test_retry_uses_rate_limit_retry_after(self):
        """RateLimitError 携带 retry_after 时，sleep 使用 retry_after 而非默认延迟"""
        attempts = {"count": 0}

        @api_retry(max_retries=3, delay=1.0, backoff=2.0)
        def flaky():
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise RateLimitError("back off", retry_after=2.5)
            return "ok"

        with mock.patch("exchange.decorators.time.sleep") as mock_sleep:
            assert flaky() == "ok"
        mock_sleep.assert_called_once_with(2.5)
        assert attempts["count"] == 2

    def test_exponential_backoff_delay_sequence(self):
        """验证指数退避延迟序列：delay, delay*backoff, delay*backoff^2 ..."""

        @api_retry(max_retries=3, delay=1.0, backoff=2.0)
        def always_fail():
            raise RateLimitError("boom")

        with mock.patch("exchange.decorators.time.sleep") as mock_sleep:
            with pytest.raises(RateLimitError):
                always_fail()
        assert mock_sleep.call_count == 3
        assert mock_sleep.call_args_list == [mock.call(1.0), mock.call(2.0), mock.call(4.0)]

    def test_raises_last_exception_after_exhausting_attempts(self):
        """重试耗尽后抛出的异常被重新抛出，函数最多被调用 max_retries+1 次"""
        attempts = {"count": 0}

        @api_retry(max_retries=2, delay=0.0)
        def always_fail():
            attempts["count"] += 1
            raise RateLimitError("boom")

        with mock.patch("exchange.decorators.time.sleep"):
            with pytest.raises(RateLimitError):
                always_fail()
        assert attempts["count"] == 3

    def test_non_retryable_exception_passthrough(self):
        """非可重试异常直接向外抛，不进行任何睡眠"""

        @api_retry(max_retries=3, delay=1.0)
        def boom():
            raise ValueError("bad input")

        with mock.patch("exchange.decorators.time.sleep") as mock_sleep:
            with pytest.raises(ValueError):
                boom()
        assert mock_sleep.call_count == 0


class TestRequireConnected:
    """测试 require_connected 装饰器"""

    def test_not_connected_raises_connection_error(self):
        with pytest.raises(ConnectionError, match="not connected"):
            _StubConnected(connected=False).ping()

    def test_connected_invokes_function(self):
        assert _StubConnected(connected=True).ping() == "pong"


class TestRequireFeature:
    """测试 require_feature 装饰器"""

    def test_supported_feature_invokes_function(self):
        assert _StubExchangeFeatures().trade_spot() == "spot-ok"

    def test_unsupported_feature_raises(self):
        with pytest.raises(NotImplementedFeatureError) as exc_info:
            _StubExchangeFeatures().list_sub_accounts()
        assert exc_info.value.feature == "sub_account"
        assert exc_info.value.exchange_name == "stub"

    def test_missing_exchange_features_attr_raises(self):
        with pytest.raises(NotImplementedFeatureError):
            _NoFeaturesExchange().trade()


class TestRateLimit:
    """测试 rate_limit 装饰器"""

    def test_blocks_when_calls_exceeded(self):
        calls = []

        @rate_limit(calls=2, period=1.0)
        def hit():
            calls.append(1)

        with mock.patch("exchange.decorators.time.sleep") as mock_sleep:
            hit()
            hit()
            hit()

        assert len(calls) == 3
        mock_sleep.assert_called_once()
        sleep_time = mock_sleep.call_args.args[0]
        assert 0 < sleep_time <= 1.0

    def test_allows_calls_under_limit(self):
        calls = []

        @rate_limit(calls=5, period=1.0)
        def hit():
            calls.append(1)

        with mock.patch("exchange.decorators.time.sleep") as mock_sleep:
            for _ in range(3):
                hit()

        assert len(calls) == 3
        assert not mock_sleep.called


class TestExchangeAdapter:
    """测试 ExchangeAdapter 的 AXON 门控、非法 ID 与未连接行为"""

    def test_unavailable_raises_runtime_error(self):
        with mock.patch.object(adapter_mod, "AXON_AVAILABLE", False):
            with pytest.raises(RuntimeError, match=r"axon_quant\.exchange"):
                adapter_mod.ExchangeAdapter("binance")

    def test_unknown_exchange_raises_value_error(self):
        with mock.patch.object(adapter_mod, "AXON_AVAILABLE", True):
            with pytest.raises(ValueError, match="不支持的交易所"):
                adapter_mod.ExchangeAdapter("coinbase")

    def test_unconnected_methods_raise_runtime_error(self):
        """_adapter 为 None（未连接）时，交易类方法统一抛 RuntimeError"""
        adapter = object.__new__(adapter_mod.ExchangeAdapter)
        adapter._adapter = None
        adapter._exchange_id = "binance"

        with pytest.raises(RuntimeError, match="未连接"):
            adapter.get_ticker("BTCUSDT")
        with pytest.raises(RuntimeError, match="未连接"):
            adapter.place_order({})
        with pytest.raises(RuntimeError, match="未连接"):
            adapter.get_balance()
        with pytest.raises(RuntimeError, match="未连接"):
            adapter.get_positions()

    def test_binance_testnet_wiring(self):
        """binance+testnet 时使用 binance_testnet_config 并实例化 BinanceAdapter"""
        with (
            mock.patch.object(adapter_mod, "AXON_AVAILABLE", True),
            mock.patch.object(adapter_mod, "_BinanceAdapter") as mock_adapter_cls,
            mock.patch.object(adapter_mod, "_binance_testnet_config") as mock_cfg,
        ):
            adapter = adapter_mod.ExchangeAdapter("binance", testnet=True)

        mock_cfg.assert_called_once()
        mock_adapter_cls.assert_called_once_with(mock_cfg.return_value)
        assert adapter._adapter is mock_adapter_cls.return_value

    def test_binance_mainnet_wiring(self):
        """binance 非 testnet 时使用 ExchangeConfig(exchange_id=BINANCE, testnet=False)"""
        with (
            mock.patch.object(adapter_mod, "AXON_AVAILABLE", True),
            mock.patch.object(adapter_mod, "_BinanceAdapter"),
            mock.patch.object(adapter_mod, "_ExchangeConfig") as mock_cfg,
            mock.patch.object(adapter_mod, "_ExchangeId") as mock_eid,
        ):
            adapter_mod.ExchangeAdapter("binance", testnet=False)
        mock_cfg.assert_called_once_with(exchange_id=mock_eid.BINANCE, testnet=False)

    def test_okx_mainnet_wiring(self):
        """okx 非 testnet 时使用 ExchangeConfig(exchange_id=OKX, testnet=False) 并实例化 OkxAdapter"""
        with (
            mock.patch.object(adapter_mod, "AXON_AVAILABLE", True),
            mock.patch.object(adapter_mod, "_OkxAdapter"),
            mock.patch.object(adapter_mod, "_ExchangeConfig") as mock_cfg,
            mock.patch.object(adapter_mod, "_ExchangeId") as mock_eid,
        ):
            adapter = adapter_mod.ExchangeAdapter("okx", testnet=False)
        mock_cfg.assert_called_once_with(exchange_id=mock_eid.OKX, testnet=False)
        assert adapter._adapter is not None


class TestExchangeAdapterProxy:
    """测试 ExchangeAdapterProxy 空实现路径与代理转发"""

    def test_empty_implementation_defaults(self):
        """AXON 不可用时，全部方法返回默认空值且不抛错"""
        with mock.patch.object(adapter_mod, "AXON_AVAILABLE", False):
            proxy = adapter_mod.ExchangeAdapterProxy("binance", testnet=True)

        assert proxy.available is False
        assert proxy.get_ticker("BTCUSDT") == {}
        assert proxy.place_order({}) == {"error": "exchange not available"}
        assert proxy.cancel_order("order-1") == {"error": "exchange not available"}
        assert proxy.get_balance() == {}
        assert proxy.get_positions() == []
        assert proxy.get_depth("BTCUSDT") == {}
        proxy.connect()
        proxy.disconnect()
        proxy.subscribe(["BTCUSDT"])

    def test_delegates_to_adapter_when_available(self):
        """_available=True 时，get_ticker 等方法转发到底层 _adapter"""
        proxy = object.__new__(adapter_mod.ExchangeAdapterProxy)
        proxy._available = True
        proxy._adapter = mock.MagicMock()

        assert proxy.get_ticker("BTCUSDT") is proxy._adapter.get_ticker.return_value
        proxy._adapter.get_ticker.assert_called_once_with("BTCUSDT")
        proxy.place_order({"side": "Buy"})
        proxy._adapter.place_order.assert_called_once_with({"side": "Buy"})


class TestConnectionFactory:
    """测试 connection._create_exchange_instance 内部工厂函数"""

    def test_create_exchange_instance_binance(self):
        with mock.patch("exchange.binance.exchange.BinanceExchange") as mock_cls:
            result = connection_mod._create_exchange_instance(
                "binance",
                api_key="k",
                secret_key="s",
                trading_mode="future",
                proxy_url="http://127.0.0.1:8080",
                testnet=True,
            )
        mock_cls.assert_called_once_with(
            exchange_name="binance",
            api_key="k",
            secret_key="s",
            trading_mode="future",
            proxy_url="http://127.0.0.1:8080",
            testnet=True,
        )
        assert result is mock_cls.return_value

    def test_create_exchange_instance_okx(self):
        with mock.patch("exchange.okx.exchange.OkxExchange") as mock_cls:
            result = connection_mod._create_exchange_instance("okx")
        mock_cls.assert_called_once_with(
            exchange_name="okx",
            api_key=None,
            secret_key=None,
            trading_mode="spot",
            proxy_url=None,
            testnet=False,
        )
        assert result is mock_cls.return_value

    def test_create_exchange_instance_unsupported_raises_value_error(self):
        with pytest.raises(ValueError, match="不支持"):
            connection_mod._create_exchange_instance("coinbase")

    def test_test_exchange_connection_sync_unsupported(self):
        """不支持的交易所直接返回 UNKNOWN_ERROR 结果，不发起网络请求"""
        result = connection_mod.test_exchange_connection_sync("coinbase")
        assert result.success is False
        assert result.status == ConnectionStatus.UNKNOWN_ERROR


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
