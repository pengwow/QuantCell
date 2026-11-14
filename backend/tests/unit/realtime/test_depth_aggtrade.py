"""depth20 订阅路由与 raw payload 解析的单元测试。"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from exchange.binance.websocket_client import BinanceWebSocketClient


def _client():
    # 跳过 __init__（会建网络连接），只装配 subscribe 所需的最小状态
    client = BinanceWebSocketClient.__new__(BinanceWebSocketClient)
    client._connected = MagicMock()  # truthy：视为已连接
    client._socket_manager = MagicMock()
    client._active_sockets = {}  # 现场类型为 dict（channel -> socket）
    client.subscribed_channels = set()
    client._receive_task = MagicMock()
    # done() 必须为 falsy，否则 subscribe 末尾会另起 _receive_messages 任务
    client._receive_task.done.return_value = False
    # socket 工厂返回的 mock 需要 connect() 可被 await
    for factory in (
        client._socket_manager.depth_socket,
        client._socket_manager.aggtrade_socket,
    ):
        factory.return_value.connect = AsyncMock()
    return client


def _run(coro):
    """subscribe 是 async 方法，用 asyncio.run 同步执行（避免依赖 pytest-asyncio）"""
    return asyncio.run(coro)


def test_subscribe_depth20_routes_to_snapshot_socket():
    client = _client()
    _run(client.subscribe(["BTCUSDT@depth20"]))
    # 快照流：depth_socket(symbol=..., depth="20")，不传 interval（1s 快照推送）
    client._socket_manager.depth_socket.assert_called_once_with(symbol="BTCUSDT", depth="20")


def test_subscribe_plain_depth_routes_to_diff_socket():
    client = _client()
    _run(client.subscribe(["BTCUSDT@depth"]))
    # diff 深度流：不传 depth，保持旧行为
    client._socket_manager.depth_socket.assert_called_once_with(symbol="BTCUSDT")


def test_subscribe_depth20_with_update_suffix_routes_to_snapshot_socket():
    client = _client()
    _run(client.subscribe(["BTCUSDT@depth20@100ms"]))
    # 带 @Nms 更新频率后缀的快照流，仍按 depth= 层数订阅（后缀不透传）
    client._socket_manager.depth_socket.assert_called_once_with(symbol="BTCUSDT", depth="20")


def test_subscribe_aggtrade_routes_to_aggtrade_socket():
    client = _client()
    _run(client.subscribe(["BTCUSDT@aggTrade"]))
    client._socket_manager.aggtrade_socket.assert_called_once_with(symbol="BTCUSDT")
