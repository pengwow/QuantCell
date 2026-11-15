"""ws_fill_events 广播 helper 行为测试：信封结构 / 失败兜底 / 无队列静默。

广播是旁路观测链路：任何异常都不允许打断成交入账主流程。
用假队列/假 manager 驱动 broadcast_strategy_fill 的三条路径，
并附 live_trade_sync 模块导入冒烟（守护 except 语法修复不被回退）。
"""

import queue as queue_mod
from types import SimpleNamespace

from worker.ws_fill_events import _norm_symbol, broadcast_strategy_fill


class _FakeQueue:
    """内存队列替身：put_nowait 记录消息，可配置抛 queue.Full。"""

    def __init__(self, *, raise_full: bool = False):
        self.messages: list[dict] = []
        self._raise_full = raise_full

    def put_nowait(self, msg):
        if self._raise_full:
            raise queue_mod.Full
        self.messages.append(msg)


def test_broadcast_envelope(monkeypatch):
    """信封结构：type/topic 固定 strategy.fill，id 为 fill_<uuid12>，
    data 含 worker_id/strategy_id/symbol/side/price/quantity/ts，
    symbol 归一为无分隔大写、side 小写对齐 ccxt 口径。"""
    import websocket.manager as ws_manager

    q = _FakeQueue()
    monkeypatch.setattr(ws_manager, "manager", SimpleNamespace(message_queue=q))
    broadcast_strategy_fill(
        worker_id="7",
        strategy_id="12",
        symbol="BTC/USDT:USDT",
        side="Buy",
        price=65000.5,
        quantity=0.01,
        ts=1731532800000,
    )
    assert len(q.messages) == 1
    msg = q.messages[0]
    assert msg["type"] == "strategy.fill"
    assert msg["topic"] == "strategy.fill"
    assert msg["id"].startswith("fill_") and len(msg["id"]) == len("fill_") + 12
    assert isinstance(msg["timestamp"], int)
    data = msg["data"]
    assert data["worker_id"] == "7"
    assert data["strategy_id"] == "12"
    assert data["symbol"] == "BTCUSDT"
    assert data["side"] == "buy"
    assert data["price"] == 65000.5
    assert data["quantity"] == 0.01
    assert data["ts"] == 1731532800000


def test_broadcast_survives_queue_full(monkeypatch):
    """队列打满（put_nowait 抛 queue.Full）只降级 warning，不向落库主流程抛异常。"""
    import websocket.manager as ws_manager

    q = _FakeQueue(raise_full=True)
    monkeypatch.setattr(ws_manager, "manager", SimpleNamespace(message_queue=q))
    # 不向调用方抛出即通过：真实入账路径绝不被广播拖崩
    broadcast_strategy_fill(
        worker_id="7",
        strategy_id="",
        symbol="BTC/USDT",
        side="buy",
        price=1.0,
        quantity=1.0,
        ts=0,
    )


def test_broadcast_without_queue_is_silent(monkeypatch):
    """WS 栈未启动（message_queue 为 None 或属性缺失）时静默 return。"""
    import websocket.manager as ws_manager

    q = _FakeQueue()
    monkeypatch.setattr(ws_manager, "manager", SimpleNamespace(message_queue=None))
    broadcast_strategy_fill(
        worker_id="7",
        strategy_id="",
        symbol="BTC/USDT",
        side="buy",
        price=1.0,
        quantity=1.0,
        ts=0,
    )
    assert q.messages == []

    # manager 连 message_queue 属性都没有（getattr 默认值兜底）也不抛
    monkeypatch.setattr(ws_manager, "manager", SimpleNamespace())
    broadcast_strategy_fill(
        worker_id="7",
        strategy_id="",
        symbol="BTC/USDT",
        side="buy",
        price=1.0,
        quantity=1.0,
        ts=0,
    )


def test_norm_symbol_variants():
    """符号归一覆盖三种现场口径：DB 口径 / ccxt 永续后缀 / 中划线。"""
    assert _norm_symbol("BTC/USDT") == "BTCUSDT"
    assert _norm_symbol("BTC/USDT:USDT") == "BTCUSDT"
    assert _norm_symbol("eth-usdt") == "ETHUSDT"
    assert _norm_symbol("") == ""


def test_live_trade_sync_importable():
    """冒烟：live_trade_sync 模块（含 except 语法修复 + 广播插装）可完整导入。"""
    import worker.live_trade_sync
