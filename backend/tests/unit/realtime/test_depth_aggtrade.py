"""depth20 订阅路由与 raw payload 解析的单元测试。"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from exchange.binance.websocket_client import BinanceWebSocketClient
from realtime.data_distributor import DataDistributor
from realtime.data_processor import DataProcessor
from realtime.engine import RealtimeEngine


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


# ---------------------------------------------------------------------------
# Task 1：engine channel 信封分发 + data_processor raw 解析兼容
# ---------------------------------------------------------------------------


def _processor():
    return DataProcessor()


def _engine():
    # 跳过 __init__（会拉起全部子系统），只装配消息链路所需组件
    engine = RealtimeEngine.__new__(RealtimeEngine)
    engine.data_processor = DataProcessor()
    engine.data_distributor = DataDistributor()
    engine.monitor = MagicMock()
    return engine


def test_engine_routes_depth_channel_envelope():
    """无 \"e\" 的 depth 频道信封应经 channel 分支解析后分发到 depth 消费方"""
    engine = _engine()
    seen = []
    engine.data_distributor.register_consumer("depth", seen.append)
    raw = {
        "channel": "BTCUSDT@depth20",
        "lastUpdateId": 1,
        "bids": [["60000", "1.2"]],
        "asks": [["60000.1", "0.5"]],
    }
    engine._handle_message(raw)
    assert len(seen) == 1
    assert seen[0]["symbol"] == "BTCUSDT"
    assert seen[0]["data_type"] == "depth"
    # 浅拷贝注入：engine 内补字段不得改写 _receive_messages 持有的原消息 dict
    assert "symbol" not in raw
    assert "data_type" not in raw


def test_process_depth_raw_snapshot():
    """binance depth20 快照 raw（经 engine 注入 exchange/data_type/symbol 后的形态）"""
    out = _processor().process_message(
        {
            "exchange": "binance",
            "data_type": "depth",
            "channel": "BTCUSDT@depth20",
            "symbol": "BTCUSDT",
            "lastUpdateId": 1,
            "bids": [["60000", "1.2"]],
            "asks": [["60000.1", "0.5"]],
        }
    )
    assert out["symbol"] == "BTCUSDT"
    assert out["bids"] == [[60000.0, 1.2]]
    assert out["asks"] == [[60000.1, 0.5]]
    assert out["last_update_id"] == 1
    assert out["data_type"] == "depth"
    # 快照缺事件时间：timestamp 为接受时刻兜底的毫秒整数
    assert isinstance(out["timestamp"], int)


def test_process_depth_parsed_long_keys():
    """已解析长键形态（event_time/symbol/last_update_id）保持兼容"""
    out = _processor().process_message(
        {
            "exchange": "binance",
            "data_type": "depth",
            "symbol": "ETHUSDT",
            "event_time": 1700000000000,
            "bids": [["2000", "3"]],
            "asks": [["2000.5", "2"]],
        }
    )
    assert out["symbol"] == "ETHUSDT"
    assert out["timestamp"] == 1700000000000


def test_process_aggtrade_raw():
    """raw aggTrade 短键（e/E/s/a/p/q/f/l/T/m）可正确解析"""
    out = _processor().process_message(
        {
            "exchange": "binance",
            "data_type": "aggTrade",
            "e": "aggTrade",
            "E": 1700000000000,
            "s": "BTCUSDT",
            "a": 1,
            "p": "60000.5",
            "q": "0.01",
            "f": 10,
            "l": 12,
            "T": 1700000000001,
            "m": True,
        }
    )
    assert out["symbol"] == "BTCUSDT"
    assert out["price"] == 60000.5
    assert out["quantity"] == 0.01
    assert out["timestamp"] == 1700000000001
    assert out["is_buyer_maker"] is True


def test_process_aggtrade_missing_price_drops():
    """缺价格/数量的 aggTrade 视为不可用消息丢弃"""
    assert (
        _processor().process_message({"exchange": "binance", "data_type": "aggTrade", "s": "BTCUSDT", "q": "1"}) is None
    )
