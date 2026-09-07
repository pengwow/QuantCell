"""collector.services.kline_factory 单元测试。

覆盖 K 线数据获取器体系：
- BaseKlineFetcher: 代理配置新旧格式、数据库保存（插入/更新/异常）、ccxt 拉取与兜底、
  数据库查询及时间过滤
- CryptoSpotKlineFetcher: 数据时效性判断、过期/空数据回源 ccxt
- CryptoFutureKlineFetcher: 空数据回源 ccxt
- KlineDataFactory: 工厂分发
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from collector.services.kline_factory import (
    BaseKlineFetcher,
    CryptoFutureKlineFetcher,
    CryptoSpotKlineFetcher,
    FuturesKlineFetcher,
    KlineDataFactory,
    StockKlineFetcher,
)

BASE_KLINE = {
    "timestamp": 1704067200000,  # 毫秒
    "open": "100.5",
    "high": "102.0",
    "low": "99.0",
    "close": "101.0",
    "volume": "1000.0",
}


def make_existing_row():
    row = MagicMock()
    row.unique_kline = "BTCUSDT_1h_1704067200000000000"
    return row


class FakeTimeColumn:
    """模拟 SQLAlchemy 时间戳列。

    MagicMock 参与 >=/<= 比较会抛 TypeError，而设成纯字符串后又没有 .desc()。
    一个同时支持比较和 desc() 的最小假列即可满足 filter 与 order_by 两处调用。
    """

    def __init__(self, value="0"):
        self._value = value

    def __ge__(self, other):
        return self._value >= other

    def __le__(self, other):
        return self._value <= other

    def desc(self):
        return self


class StubKlineFetcher(BaseKlineFetcher):
    """BaseKlineFetcher 是抽象类（fetch_kline_data 为抽象方法），无法直接实例化。

    这里提供一个最小实现子类，用于测试基类里的通用方法
    （代理配置 / 保存 / ccxt 拉取 / 数据库查询）。
    """

    def fetch_kline_data(self, db, symbol, interval, start_time=None, end_time=None, limit=5000):
        return self._fetch_from_database(db, symbol, interval, start_time, end_time, limit)


# =================== 代理配置 ===================


class TestGetProxyConfig:
    def test_new_nested_format_and_truthy_conversion(self):
        with patch(
            "utils.config_manager.load_system_configs",
            return_value={
                "exchange.binance.proxy_enabled": "1",
                "exchange.binance.proxy_url": "http://p:8080",
            },
        ):
            cfg = StubKlineFetcher()._get_proxy_config()
        assert cfg["enabled"] is True
        assert cfg["url"] == "http://p:8080"

    def test_legacy_flat_format(self):
        with patch(
            "utils.config_manager.load_system_configs",
            return_value={"proxy_enabled": True, "proxy_url": "socks5://localhost:1080"},
        ):
            cfg = StubKlineFetcher()._get_proxy_config()
        assert cfg["enabled"] is True

    def test_nested_present_but_disabled_does_not_fallback(self):
        with patch(
            "utils.config_manager.load_system_configs",
            return_value={"exchange.binance.proxy_enabled": "0"},
        ):
            cfg = StubKlineFetcher()._get_proxy_config()
        assert cfg["enabled"] is False
        assert cfg["url"] is None


# =================== 保存到数据库 ===================


class TestSaveToDatabase:
    def test_save_without_model_returns_false(self):
        fetcher = StubKlineFetcher()
        fetcher.kline_model = None
        assert fetcher._save_to_database(MagicMock(), "BTCUSDT", "1h", [BASE_KLINE]) is False

    def test_insert_new_rows(self):
        fetcher = StubKlineFetcher()
        fetcher.kline_model = MagicMock(__tablename__="crypto_spot_kline")
        db = MagicMock()
        # first() 返回 None -> 全部走新增分支
        db.query.return_value.filter.return_value.first.return_value = None

        ok = fetcher._save_to_database(db, "BTCUSDT", "1h", [BASE_KLINE])
        assert ok is True
        db.add.assert_called_once()
        db.commit.assert_called_once()

    def test_update_existing_row(self):
        fetcher = StubKlineFetcher()
        # __tablename__ 是 dunder 属性，不走 MagicMock 的 __getattr__，
        # 生产模型自带该属性，这里显式配置避免日志行抛 AttributeError
        fetcher.kline_model = MagicMock(__tablename__="crypto_spot_kline")
        db = MagicMock()
        existing = make_existing_row()
        db.query.return_value.filter.return_value.first.return_value = existing

        ok = fetcher._save_to_database(db, "BTCUSDT", "1h", [BASE_KLINE])
        assert ok is True
        assert existing.open == "100.5"
        assert existing.close == "101.0"
        assert existing.data_source == "ccxt_binance"
        db.add.assert_not_called()

    def test_exception_rolls_back(self):
        fetcher = StubKlineFetcher()
        fetcher.kline_model = MagicMock(__tablename__="crypto_spot_kline")
        db = MagicMock()
        db.query.side_effect = RuntimeError("boom")
        assert fetcher._save_to_database(db, "BTCUSDT", "1h", [BASE_KLINE]) is False
        db.rollback.assert_called_once()


# =================== ccxt 拉取 ===================


class TestFetchFromCcxt:
    def test_success_converts_ohlcv(self):
        fetcher = StubKlineFetcher()
        ohlcv = [[1704067200000, "100.5", "102.0", "99.0", "101.0", "1000"]]
        with patch("ccxt.binance") as mock_cls:
            mock_cls.return_value.fetchOHLCV.return_value = ohlcv
            data = fetcher._fetch_from_ccxt("BTC/USDT", "1h", limit=100)
        assert len(data) == 1
        assert data[0]["timestamp"] == 1704067200000
        assert data[0]["open"] == 100.5
        assert data[0]["close"] == 101.0
        assert data[0]["volume"] == 1000.0
        assert data[0]["turnover"] == 0.0

    def test_http_proxy_and_auth_applied(self):
        fetcher = StubKlineFetcher()
        with patch("ccxt.binance") as mock_cls:
            exchange = mock_cls.return_value
            exchange.fetchOHLCV.return_value = [[1, 2, 3, 4, 5, 6]]
            fetcher._fetch_from_ccxt(
                "BTC/USDT",
                "1h",
                proxy_config={
                    "enabled": True,
                    "url": "http://proxy:8080",
                    "username": "u",
                    "password": "p",
                },
            )
        assert exchange.proxies == {"http": "http://proxy:8080", "https": "http://proxy:8080"}
        assert exchange.proxy_auth == ("u", "p")

    def test_socks_proxy_uses_proxy_attr(self):
        with patch("ccxt.binance") as mock_cls:
            exchange = mock_cls.return_value
            exchange.fetchOHLCV.return_value = []
            StubKlineFetcher()._fetch_from_ccxt(
                "BTC/USDT", "1h", proxy_config={"enabled": True, "url": "socks5://h:1080"}
            )
        assert exchange.proxy == "socks5://h:1080"

    def test_exception_returns_empty(self):
        with patch("ccxt.binance") as mock_cls:
            mock_cls.return_value.fetchOHLCV.side_effect = Exception("network down")
            data = StubKlineFetcher()._fetch_from_ccxt("BTC/USDT", "1h")
        assert data == []


# =================== 从数据库获取 ===================


def make_db_klines(klines):
    db = MagicMock()
    query = db.query.return_value
    query.filter.return_value = query
    query.order_by.return_value = query
    query.limit.return_value = query
    query.all.return_value = klines
    return db


def make_kline_row(ts_ns="1704067200000000000", open_="100.5", close_="101.0"):
    row = MagicMock()
    row.timestamp = ts_ns
    row.open = open_
    row.high = "102.0"
    row.low = "99.0"
    row.close = close_
    row.volume = "1000.0"
    return row


class TestFetchFromDatabase:
    def test_without_model_returns_failure(self):
        fetcher = StubKlineFetcher()
        fetcher.kline_model = None
        result = fetcher._fetch_from_database(MagicMock(), "BTCUSDT", "1h")
        assert result["success"] is False

    def test_returns_ms_timestamps_and_ascending(self):
        fetcher = StubKlineFetcher()
        fetcher.kline_model = MagicMock()
        # 业务按时间降序查询（order_by desc），mock 需按降序喂数据，
        # 业务内部 reverse 后对外返回升序
        db = make_db_klines([make_kline_row("1704067260000000000"), make_kline_row("1704067200000000000")])
        result = fetcher._fetch_from_database(db, "BTCUSDT", "1h")
        assert result["success"] is True
        timestamps = [k["timestamp"] for k in result["kline_data"]]
        assert timestamps == [1704067200000, 1704067260000]
        assert result["kline_data"][0]["open"] == 100.5

    def test_invalid_start_time_is_ignored(self):
        fetcher = StubKlineFetcher()
        fetcher.kline_model = MagicMock()
        db = make_db_klines([make_kline_row()])
        # 非法时间格式应被忽略而不是崩溃
        result = fetcher._fetch_from_database(db, "BTCUSDT", "1h", start_time="not-a-date")
        assert result["success"] is True

    def test_valid_start_time_applies_filter(self):
        fetcher = StubKlineFetcher()
        fetcher.kline_model = MagicMock()
        # 有效时间过滤要对 timestamp 做 >= 比较，同时 order_by 还要调用 .desc()
        fetcher.kline_model.timestamp = FakeTimeColumn("0")
        db = make_db_klines([make_kline_row()])
        # 有效时间应触发时间过滤 -> 调用 datetime_to_nanoseconds 并追加时间戳条件
        result = fetcher._fetch_from_database(db, "BTCUSDT", "1h", start_time="2024-01-01 00:00:00")
        assert result["success"] is True
        filter_calls = db.query.return_value.filter.call_args_list
        # 第一个是 symbol+interval，第二个是时间戳 >= start_time 过滤
        assert len(filter_calls) == 2


# =================== 时效性 ===================


class TestFreshness:
    def setup_method(self):
        self.fetcher = CryptoSpotKlineFetcher()

    def test_interval_map(self):
        assert self.fetcher._get_interval_ms("5m") == 300_000
        assert self.fetcher._get_interval_ms("1d") == 86_400_000
        assert self.fetcher._get_interval_ms("bogus") == 60_000

    def test_fresh_data(self):
        now_ms = int(datetime.now(UTC).timestamp() * 1000)
        expired, reason = self.fetcher._is_data_expired(now_ms - 10_000, "1h")
        assert expired is False
        assert reason == "数据新鲜"

    def test_expired_by_period(self):
        now_ms = int(datetime.now(UTC).timestamp() * 1000)
        expired, reason = self.fetcher._is_data_expired(now_ms - 2 * 3_600_000, "1h")
        assert expired is True
        assert "超过1根K线周期" in reason


# =================== 现货 fetch 链路 ===================


class TestCryptoSpotFetch:
    def test_db_fresh_skips_ccxt(self):
        fetcher = CryptoSpotKlineFetcher()
        now_ms = int(datetime.now(UTC).timestamp() * 1000)
        # 数据库返回的 timestamp 已转为毫秒，10 秒前属于新鲜数据
        fresh_ts = now_ms - 10_000
        db_result = {
            "success": True,
            "message": "查询K线数据成功",
            "kline_data": [{"timestamp": fresh_ts, "open": 1.0, "close": 1.0, "high": 1.0, "low": 1.0, "volume": 1.0}],
        }
        with (
            patch.object(fetcher, "_fetch_from_database", return_value=db_result),
            patch.object(fetcher, "_fetch_from_ccxt") as m_ccxt,
            patch.object(fetcher, "_save_to_database") as m_save,
        ):
            result = fetcher.fetch_kline_data(MagicMock(), "BTC/USDT", "1h")
        m_ccxt.assert_not_called()
        m_save.assert_not_called()
        assert result["success"] is True

    def test_db_empty_fetches_from_ccxt_and_saves(self):
        fetcher = CryptoSpotKlineFetcher()
        db = MagicMock()
        db_empty = {"success": True, "message": "查询K线数据成功", "kline_data": []}
        ccxt_data = [{"timestamp": 1704067200000, "open": 1, "close": 1, "high": 1, "low": 1, "volume": 1}]
        with (
            patch.object(fetcher, "_fetch_from_database", return_value=db_empty) as m_db,
            patch.object(fetcher, "_fetch_from_ccxt", return_value=ccxt_data),
            patch.object(fetcher, "_save_to_database") as m_save,
        ):
            result = fetcher.fetch_kline_data(db, "BTC/USDT", "1h")
        assert result["kline_data"] == ccxt_data
        assert result["message"] == "从ccxt获取K线数据成功"
        # symbol 应格式化为 BTCUSDT 保存
        m_save.assert_called_once_with(db, "BTCUSDT", "1h", ccxt_data)
        m_db.assert_called_once()

    def test_ccxt_also_empty_keeps_error_state(self):
        fetcher = CryptoSpotKlineFetcher()
        db_result = {"success": True, "message": "查询K线数据成功", "kline_data": []}
        with (
            patch.object(fetcher, "_fetch_from_database", return_value=db_result),
            patch.object(fetcher, "_fetch_from_ccxt", return_value=[]),
            patch.object(fetcher, "_save_to_database"),
        ):
            result = fetcher.fetch_kline_data(MagicMock(), "BTC/USDT", "1h")
        assert result["message"] == "数据库和ccxt均未找到K线数据"


# =================== 合约 fetch ===================


class TestCryptoFutureFetch:
    def test_db_has_data_skips_ccxt(self):
        fetcher = CryptoFutureKlineFetcher()
        db_result = {
            "success": True,
            "message": "查询K线数据成功",
            "kline_data": [{"timestamp": 1704067200000, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}],
        }
        with (
            patch.object(fetcher, "_fetch_from_database", return_value=db_result),
            patch.object(fetcher, "_fetch_from_ccxt") as m_ccxt,
        ):
            result = fetcher.fetch_kline_data(MagicMock(), "BTC/USDT", "1h")
        m_ccxt.assert_not_called()
        assert result["kline_data"]

    def test_db_empty_fetches_ccxt(self):
        fetcher = CryptoFutureKlineFetcher()
        db_result = {"success": True, "message": "查询K线数据成功", "kline_data": []}
        ccxt_data = [{"timestamp": 1704067200000, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}]
        with (
            patch.object(fetcher, "_fetch_from_database", return_value=db_result),
            patch.object(fetcher, "_fetch_from_ccxt", return_value=ccxt_data),
            patch.object(fetcher, "_save_to_database") as m_save,
        ):
            result = fetcher.fetch_kline_data(MagicMock(), "BTC/USDT", "1h")
        assert result["message"] == "从ccxt获取K线数据成功"
        m_save.assert_called_once()


# =================== 工厂 ===================


class TestKlineDataFactory:
    def test_all_branches(self):
        assert isinstance(KlineDataFactory.create_fetcher("stock"), StockKlineFetcher)
        assert isinstance(KlineDataFactory.create_fetcher("futures"), FuturesKlineFetcher)

    def test_crypto_branches(self):
        assert isinstance(KlineDataFactory.create_fetcher("crypto", "spot"), CryptoSpotKlineFetcher)
        assert isinstance(KlineDataFactory.create_fetcher("crypto", "future"), CryptoFutureKlineFetcher)

    def test_invalid_types_raise(self):
        with pytest.raises(ValueError, match="无效的加密货币类型"):
            KlineDataFactory.create_fetcher("crypto", "bogus")
        with pytest.raises(ValueError):
            KlineDataFactory.create_fetcher("bogus")
