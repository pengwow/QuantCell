"""depth/trades 广播消费者的节流与攒批行为。"""

import queue as queue_mod

from realtime.ws_push import make_aggtrade_push_consumer, make_depth_push_consumer


class FakeQueue:
    """模拟 asyncio.Queue 的 put_nowait 侧接口（消费者只依赖这一个方法）"""

    def __init__(self):
        self.items = []

    def put_nowait(self, item):
        self.items.append(item)


class FakeManager:
    """只需暴露 message_queue 属性，与 websocket.manager 的消费面一致"""

    def __init__(self):
        self.message_queue = FakeQueue()


def test_depth_consumer_throttles_per_symbol():
    mgr = FakeManager()
    q = mgr.message_queue
    t = [0.0]
    consumer = make_depth_push_consumer(mgr, throttle=0.5, clock=lambda: t[0])
    consumer({"symbol": "BTCUSDT", "bids": [[1, 1]], "asks": [[2, 1]], "data_type": "depth"})
    t[0] = 0.2  # 未过节流窗口，被节流
    consumer({"symbol": "BTCUSDT", "bids": [[1, 1]], "asks": [[2, 1]]})
    assert len(q.items) == 1
    t[0] = 0.6
    consumer({"symbol": "BTCUSDT", "bids": [[3, 1]], "asks": [[4, 1]]})
    assert len(q.items) == 2
    envelope = q.items[0]
    assert envelope["type"] == "depth"
    assert envelope["topic"] == "depth"
    assert envelope["data"] == {"symbol": "BTCUSDT", "bids": [[1, 1]], "asks": [[2, 1]]}
    assert isinstance(envelope["timestamp"], int)


def test_depth_consumer_missing_symbol_drops():
    mgr = FakeManager()
    consumer = make_depth_push_consumer(mgr)
    consumer({"bids": [[1, 1]], "asks": []})
    assert mgr.message_queue.items == []


def test_aggtrade_consumer_batches_window():
    mgr = FakeManager()
    q = mgr.message_queue
    t = [0.0]
    push = make_aggtrade_push_consumer(mgr, flush_interval=0.2, clock=lambda: t[0])
    push(
        {
            "exchange": "binance",
            "data_type": "aggTrade",
            "symbol": "BTCUSDT",
            "price": 1.0,
            "quantity": 1,
            "timestamp": 1,
            "is_buyer_maker": False,
        }
    )
    assert q.items == []  # 窗口内攒批
    t[0] = 0.3
    push(
        {
            "exchange": "binance",
            "data_type": "aggTrade",
            "symbol": "BTCUSDT",
            "price": 1.1,
            "quantity": 2,
            "timestamp": 2,
            "is_buyer_maker": True,
        }
    )
    envelope = q.items[0]
    assert envelope["type"] == "trades"
    assert envelope["topic"] == "trades"
    assert len(envelope["data"]) == 2
    # 信封内成交条目：data_processor 的 timestamp（ms）映射为 time 字段
    assert envelope["data"][1] == {
        "symbol": "BTCUSDT",
        "price": 1.1,
        "quantity": 2,
        "time": 2,
        "is_buyer_maker": True,
    }


def _mgr_with(q):
    """构造 message_queue 指向指定队列的假 manager"""
    mgr = FakeManager()
    mgr.message_queue = q
    return mgr


def test_aggtrade_queue_full_does_not_raise():
    q = FakeQueue()

    def boom(_item):
        raise queue_mod.Full  # asyncio.QueueFull 即 queue.Full，消费者必须兜住

    q.put_nowait = boom
    push = make_aggtrade_push_consumer(_mgr_with(q))
    push({"symbol": "BTCUSDT", "price": 1.0, "quantity": 1, "timestamp": 1})  # 不应抛异常
    push({"symbol": "BTCUSDT", "price": 1.0, "quantity": 1, "timestamp": 2})


def test_aggtrade_message_queue_none_no_raise():
    """message_queue 尚未初始化（manager.start 未跑）时静默丢弃，不抛异常"""

    class _NoQueue:
        pass

    naked = _NoQueue()
    for push in (make_aggtrade_push_consumer(naked), make_depth_push_consumer(naked)):
        push({"symbol": "BTCUSDT", "price": 1.0, "quantity": 1, "bids": [[1, 1]], "asks": [[2, 1]]})


def _mgr_with(q):
    """构造 message_queue 指向指定队列的假 manager"""
    mgr = FakeManager()
    mgr.message_queue = q
    return mgr
