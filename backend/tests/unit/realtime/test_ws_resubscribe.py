# 断流自愈（_run_resubscribe_due）最小单测：守护「socket 死掉后必须重订阅」的行为
import asyncio

from exchange.binance.websocket_client import BinanceWebSocketClient


def _client_with_stub_subscribe(fail_times: int):
    """构造最小实例（绕开网络初始化），stub 掉 subscribe：前 fail_times 次失败"""
    client = object.__new__(BinanceWebSocketClient)
    client.subscribed_channels = {"BTCUSDT@aggTrade"}
    client._active_sockets = {}
    client._resubscribe_due = {"BTCUSDT@aggTrade": [0.0, 0]}
    calls = {"n": 0}

    async def fake_subscribe(channels):
        calls["n"] += 1
        if calls["n"] > fail_times:
            client._active_sockets[channels[0]] = object()
            return True
        return False

    client.subscribe = fake_subscribe
    return client, calls


def test_resubscribe_retries_with_backoff_until_success():
    client, calls = _client_with_stub_subscribe(fail_times=1)
    asyncio.run(client._run_resubscribe_due())
    # 第一次失败：pending 保留、退避 2s、attempts 递增
    assert calls["n"] == 1
    assert client._resubscribe_due["BTCUSDT@aggTrade"][1] == 1
    assert client._resubscribe_due["BTCUSDT@aggTrade"][0] > 0

    # 未到退避时刻：不重试
    asyncio.run(client._run_resubscribe_due())
    assert calls["n"] == 1

    # 到期后重试成功：pending 清除
    client._resubscribe_due["BTCUSDT@aggTrade"][0] = 0.0
    asyncio.run(client._run_resubscribe_due())
    assert calls["n"] == 2
    assert "BTCUSDT@aggTrade" not in client._resubscribe_due


def test_resubscribe_stops_after_explicit_unsubscribe():
    client, calls = _client_with_stub_subscribe(fail_times=99)
    client.subscribed_channels.clear()
    asyncio.run(client._run_resubscribe_due())
    assert calls["n"] == 0
    assert not client._resubscribe_due
