"""KlineSubscriptionManager 单元测试

覆盖订阅/退订/推送/指标等核心逻辑，并回归验证 unsubscribe_all 的锁重入
死锁修复（asyncio.Lock 不可重入，需走 _unsubscribe_locked）。
"""

import asyncio
import time
import unittest.mock as mock

import pytest

from realtime.kline_subscription import KlineSubscriptionManager


def run(coro):
    """同步包装异步用例，避免依赖 pytest-asyncio 插件"""
    return asyncio.run(coro)


class TestParseTopic:
    def test_valid_topic(self):
        mgr = KlineSubscriptionManager()
        assert mgr.parse_topic("kline:BTCUSDT:1m") == ("BTCUSDT", "1m")

    def test_symbol_upper_interval_lower(self):
        mgr = KlineSubscriptionManager()
        assert mgr.parse_topic("kline:btcusdt:1D") == ("BTCUSDT", "1d")

    def test_wrong_prefix(self):
        mgr = KlineSubscriptionManager()
        assert mgr.parse_topic("trade:BTCUSDT:1m") is None

    def test_wrong_segment_count(self):
        mgr = KlineSubscriptionManager()
        assert mgr.parse_topic("kline:BTCUSDT") is None
        assert mgr.parse_topic("kline:BTCUSDT:1m:extra") is None

    def test_unsupported_interval(self):
        mgr = KlineSubscriptionManager()
        assert mgr.parse_topic("kline:BTCUSDT:2s") is None

    def test_exception_returns_none(self):
        mgr = KlineSubscriptionManager()
        with mock.patch.object(mgr, "SUPPORTED_INTERVALS", None):
            assert mgr.parse_topic("kline:BTCUSDT:1m") is None

    def test_build_topic(self):
        mgr = KlineSubscriptionManager()
        assert mgr.build_topic("btcusdt", "1M") == "kline:BTCUSDT:1m"
        assert mgr.build_topic("ETHUSDT", "5m") == "kline:ETHUSDT:5m"


class TestSubscribeUnsubscribe:
    async def _subscribed_pair(self):
        mgr = KlineSubscriptionManager()
        ok = await mgr.subscribe("c1", "BTCUSDT", "1m")
        assert ok is True
        return mgr

    def test_subscribe_creates_subscription(self):
        mgr = run(self._subscribed_pair())
        assert mgr.get_subscribed_clients("BTCUSDT", "1m") == {"c1"}
        assert mgr.get_supported_intervals() == KlineSubscriptionManager.SUPPORTED_INTERVALS

    def test_subscribe_idempotent(self):
        mgr = KlineSubscriptionManager()
        assert run(mgr.subscribe("c1", "btcusdt", "1M")) is True
        assert run(mgr.subscribe("c1", "BTCUSDT", "1m")) is True
        assert mgr.get_subscribed_clients("BTCUSDT", "1m") == {"c1"}
        assert mgr._metrics.total_subscriptions == 1
        assert mgr._metrics.active_connections == 1

    def test_subscribe_unsupported_interval_returns_false(self):
        mgr = KlineSubscriptionManager()
        assert run(mgr.subscribe("c1", "BTCUSDT", "9x")) is False
        assert mgr.get_all_subscriptions() == []

    def test_subscribe_exception_bubbles_as_false(self):
        mgr = KlineSubscriptionManager()
        with mock.patch.object(mgr, "SUPPORTED_INTERVALS", None):
            ok = run(mgr.subscribe("c1", "BTCUSDT", "1m"))
        assert ok is False

    def test_multiple_clients(self):
        mgr = KlineSubscriptionManager()
        run(mgr.subscribe("c1", "BTCUSDT", "1m"))
        run(mgr.subscribe("c2", "BTCUSDT", "1m"))
        run(mgr.subscribe("c1", "ETHUSDT", "5m"))
        assert mgr.get_subscribed_clients("BTCUSDT", "1m") == {"c1", "c2"}
        assert mgr.get_subscribed_clients("ETHUSDT", "5m") == {"c1"}
        assert mgr._metrics.active_connections == 2
        assert mgr._metrics.total_subscriptions == 2

    def test_unsubscribe_removes_client_and_cleans_empty(self):
        mgr = KlineSubscriptionManager()
        run(mgr.subscribe("c1", "BTCUSDT", "1m"))
        run(mgr.subscribe("c2", "BTCUSDT", "1m"))
        assert run(mgr.unsubscribe("c1", "BTCUSDT", "1m")) is True
        assert mgr.get_subscribed_clients("BTCUSDT", "1m") == {"c2"}
        assert run(mgr.unsubscribe("c2", "BTCUSDT", "1m")) is True
        assert mgr.get_all_subscriptions() == []
        assert mgr._client_subscriptions == {}

    def test_unsubscribe_missing_client_is_true(self):
        mgr = KlineSubscriptionManager()
        run(mgr.subscribe("c1", "BTCUSDT", "1m"))
        assert run(mgr.unsubscribe("nobody", "BTCUSDT", "1m")) is True
        assert mgr.get_subscribed_clients("BTCUSDT", "1m") == {"c1"}

    def test_unsubscribe_all_regression_no_deadlock(self):
        """回归：unsubscribe_all 曾因锁重入而死锁，修复后应正常退订全部"""
        mgr = KlineSubscriptionManager()
        run(mgr.subscribe("c1", "BTCUSDT", "1m"))
        run(mgr.subscribe("c1", "ETHUSDT", "5m"))
        run(mgr.subscribe("c1", "SOLUSDT", "15m"))
        run(mgr.subscribe("c2", "BTCUSDT", "1m"))

        ok = run(asyncio.wait_for(mgr.unsubscribe_all("c1"), timeout=2))
        assert ok is True
        assert mgr.get_client_subscriptions("c1") == []
        # c2 的订阅不受影响
        assert mgr.get_subscribed_clients("BTCUSDT", "1m") == {"c2"}
        assert mgr._metrics.active_connections == 1

    def test_unsubscribe_all_unknown_client_is_true(self):
        mgr = KlineSubscriptionManager()
        assert run(mgr.unsubscribe_all("ghost")) is True


class TestPushKline:
    def test_push_no_clients(self):
        mgr = KlineSubscriptionManager()
        result = run(mgr.push_kline("BTCUSDT", "1m", {"close": 1.0}))
        assert result == {
            "success": False,
            "target_clients": 0,
            "pushed_clients": 0,
            "failed_clients": 0,
            "latency_ms": 0,
        }

    def test_push_calls_callbacks(self):
        mgr = KlineSubscriptionManager()
        run(mgr.subscribe("c1", "BTCUSDT", "1m"))
        run(mgr.subscribe("c2", "BTCUSDT", "1m"))
        seen = []
        mgr.register_push_callback(lambda client_id, topic, msg: seen.append((client_id, topic, msg)))

        result = run(mgr.push_kline("btcusdt", "1M", {"close": 42.0}))
        assert result["success"] is True
        assert result["target_clients"] == 2
        assert result["pushed_clients"] == 2
        assert result["failed_clients"] == 0
        assert len(seen) == 2
        client_ids = {s[0] for s in seen}
        assert client_ids == {"c1", "c2"}
        topic, message = seen[0][1], seen[0][2]
        assert topic == "kline:BTCUSDT:1m"
        assert message["type"] == "kline"
        # 推送的数据原样传递
        assert message["data"] == {"close": 42.0}
        # 时间戳统一为纳秒
        assert message["timestamp"] > 10**15
        assert message["id"].startswith("kline_")

    def test_push_callback_error_counts_failure(self):
        mgr = KlineSubscriptionManager()
        run(mgr.subscribe("c1", "BTCUSDT", "1m"))

        def boom(*_args, **_kwargs):
            raise RuntimeError("boom")

        mgr.register_push_callback(boom)
        result = run(mgr.push_kline("BTCUSDT", "1m", {"close": 1.0}))
        assert result["success"] is True
        assert result["pushed_clients"] == 0
        assert result["failed_clients"] == 1
        sub = mgr.get_all_subscriptions()[0]
        assert sub["error_count"] == 1

    def test_push_updates_stats(self):
        mgr = KlineSubscriptionManager()
        run(mgr.subscribe("c1", "BTCUSDT", "1m"))
        mgr.register_push_callback(lambda *_a, **_k: None)
        # push_kline 内部共调用 5 次 time.time()（start_time、消息id、timestamp、last_push_at、latency），
        # 序列需按调用顺序一一提供
        with mock.patch(
            "realtime.kline_subscription.time.time",
            side_effect=[100.0, 100.01, 100.02, 100.03, 100.04],
        ):
            run(mgr.push_kline("BTCUSDT", "1m", {"close": 1.0}))
        sub = mgr.get_all_subscriptions()[0]
        assert sub["push_count"] == 1
        assert sub["last_push_at"] == 100.03
        latency = mgr._metrics.avg_push_latency
        assert 0 < latency < 50


class TestMetricsAndQueries:
    def test_get_metrics_shape(self):
        mgr = KlineSubscriptionManager()
        run(mgr.subscribe("c1", "BTCUSDT", "1m"))
        metrics = mgr.get_metrics()
        assert metrics["total_subscriptions"] == 1
        assert metrics["active_connections"] == 1
        assert metrics["total_pushes"] == 0

    def test_get_subscribed_clients_returns_copy(self):
        mgr = KlineSubscriptionManager()
        run(mgr.subscribe("c1", "BTCUSDT", "1m"))
        clients = mgr.get_subscribed_clients("BTCUSDT", "1m")
        clients.add("stray")
        assert mgr.get_subscribed_clients("BTCUSDT", "1m") == {"c1"}

    def test_get_client_subscriptions(self):
        mgr = KlineSubscriptionManager()
        run(mgr.subscribe("c1", "BTCUSDT", "1m"))
        run(mgr.subscribe("c1", "ETHUSDT", "5m"))
        subs = {s["symbol"] for s in mgr.get_client_subscriptions("c1")}
        assert subs == {"BTCUSDT", "ETHUSDT"}
        assert mgr.get_client_subscriptions("nobody") == []

    def test_get_all_subscriptions_fields(self):
        mgr = KlineSubscriptionManager()
        run(mgr.subscribe("c1", "BTCUSDT", "1m"))
        assert mgr.get_all_subscriptions() == [
            {
                "symbol": "BTCUSDT",
                "interval": "1m",
                "client_count": 1,
                "clients": ["c1"],
                "created_at": mock.ANY,
                "last_push_at": None,
                "push_count": 0,
                "error_count": 0,
            }
        ]

    def test_is_subscribed(self):
        mgr = KlineSubscriptionManager()
        run(mgr.subscribe("c1", "BTCUSDT", "1m"))
        assert mgr.is_subscribed("c1", "BTCUSDT", "1m") is True
        assert mgr.is_subscribed("c2", "BTCUSDT", "1m") is False
        assert mgr.is_subscribed("c1", "ETHUSDT", "1m") is False

    def test_unregister_callback(self):
        mgr = KlineSubscriptionManager()
        calls = []

        def cb(*a, **k):
            calls.append(1)

        mgr.register_push_callback(cb)
        assert mgr.unregister_push_callback(cb) is True
        assert mgr.unregister_push_callback(cb) is False
        run(mgr.subscribe("c1", "BTCUSDT", "1m"))
        run(mgr.push_kline("BTCUSDT", "1m", {"close": 1.0}))
        assert calls == []
