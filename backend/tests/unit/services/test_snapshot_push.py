"""kernel.snapshot 轮询推送验收（Task 4）。

覆盖：
1. `_push_kernel_snapshot` 消息形状转换：{"event": "kernel.snapshot", ...}；
2. paper 泵轮末尾推送（真实 PaperDriver 同步直调，与 Task 2 冒烟同套路）；
3. live tick 线程节流：15s 窗口内只推首轮，窗口归零时逐轮推；
4. broadcast_threadsafe 在主 loop 未就绪时静默丢弃。

不联网、不启动 FastAPI：WS 广播口直接 patch，驱动线程手工起停。
"""

import threading

from worker.state import connection_manager
from worker.strategy_manager import StrategyManager


def _capture_broadcast(monkeypatch):
    """把 connection_manager.broadcast_threadsafe 换成进程内消息收集器。"""
    sent: list[dict] = []
    monkeypatch.setattr(connection_manager, "broadcast_threadsafe", sent.append)
    return sent


# 两根已收市的 1h K 线（binance 原始行，openTime 远早于 now → 必然已收市）
_CLOSED_KLINES = [
    ["1700000000000", "50000.0", "50100.0", "49900.0", "50050.0", "10.0"],
    ["1700003600000", "50050.0", "50300.0", "50000.0", "50200.0", "12.0"],
]


def test_push_kernel_snapshot_shape(monkeypatch):
    """snapshot dict → kernel.snapshot 事件；非 dict 快照静默跳过。"""
    sent = _capture_broadcast(monkeypatch)
    StrategyManager._push_kernel_snapshot(42, {"equity": 99500.5, "positions": {"BTC/USDT": 0.2}})
    assert sent == [{"event": "kernel.snapshot", "worker_id": 42, "equity": 99500.5, "positions": {"BTC/USDT": 0.2}}]
    # 非法快照静默：不推送也不抛
    StrategyManager._push_kernel_snapshot(42, None)
    assert len(sent) == 1


def test_paper_pump_round_pushes_snapshot(monkeypatch):
    """泵轮末尾推送与 driver.snapshot() 同口径（RL paper / 规则 paper 共用）。"""
    monkeypatch.setattr(StrategyManager, "_paper_fetch_klines", lambda self, *args, **kwargs: _CLOSED_KLINES)
    sent = _capture_broadcast(monkeypatch)
    mgr = StrategyManager(max_workers=1)
    try:
        from axon_quant import Action, ActionType

        from strategy.base import BaseStrategy, StrategyConfig

        class _HoldStrategy(BaseStrategy):
            def __init__(self):
                super().__init__(StrategyConfig(name="hold_snap", symbol="BTCUSDT"))

            def on_bar(self, bar, ctx=None):
                return Action(ActionType.Hold, 0.0, 0.0, "hold_snap", 0)

        driver, _risk_enabled = mgr._assemble_rule_paper_driver(1, _HoldStrategy(), {}, "1h", ["BTCUSDT"])
        try:
            driver.start()
            mgr._paper_pump_round(1, driver, ["BTC/USDT"], "1h", {}, limit=2)
        finally:
            driver.shutdown()

        assert len(sent) == 1, f"泵轮应恰好推送一次，实际 {sent}"
        snap = sent[0]
        assert snap["event"] == "kernel.snapshot" and snap["worker_id"] == 1
        assert snap["equity"] is not None and isinstance(snap["positions"], dict)
    finally:
        mgr.shutdown()


def test_broadcast_threadsafe_without_loop_is_noop():
    """主 loop 未就绪（测试进程/启动早期）时静默丢弃，不排队不报错。"""
    connection_manager.main_loop = None
    connection_manager.broadcast_threadsafe({"event": "kernel.snapshot", "worker_id": 1})
    connection_manager.main_loop = None  # 断言后回到初始态，不污染其他用例


def test_live_thread_throttles_snapshot(monkeypatch, tmp_path):
    """live tick 线程节流：默认窗口只推首轮；窗口归零逐轮推。"""
    import pytest

    pytest.importorskip("axon_quant")

    monkeypatch.setattr("worker.strategy_manager._LIVE_TICK_INTERVAL_S", 0.01)

    class FakeLiveDriver:
        def __init__(self):
            self.tick_calls = 0
            self.snap_calls = 0

        def connect(self):
            pass

        def start(self, journal):
            pass

        def tick(self):
            self.tick_calls += 1
            if self.tick_calls == 5:
                done.set()

        def snapshot(self):
            self.snap_calls += 1
            return {"equity": 1.0, "positions": {}}

        def shutdown(self):
            pass

    def _run_thread() -> FakeLiveDriver:
        driver = FakeLiveDriver()
        stop = threading.Event()
        t = threading.Thread(
            target=mgr._driver_live_thread_main,
            args=(5, driver, str(tmp_path / "worker_5.jsonl"), stop),
            daemon=True,
        )
        t.start()
        assert done.wait(timeout=5), "驱动线程未在超时前完成 5 轮 tick"
        stop.set()
        t.join(timeout=5)
        return driver

    _capture_broadcast(monkeypatch)  # 主 loop None 场景下真实口也安全，这里仅防泄漏
    mgr = StrategyManager(max_workers=1)

    # 默认 15s 窗口：5 轮 tick（远小于 15s）只推首轮 1 次
    done = threading.Event()
    driver = _run_thread()
    assert driver.tick_calls == 5
    assert driver.snap_calls == 1, f"15s 节流下 5 轮只应推 1 次，实际 {driver.snap_calls}"

    # 窗口归零：逐轮推，5 轮 tick 推 5 次
    monkeypatch.setattr("worker.strategy_manager._LIVE_SNAPSHOT_INTERVAL_S", 0.0)
    done = threading.Event()
    driver = _run_thread()
    assert driver.snap_calls == 5, f"窗口归零应逐轮推，实际 {driver.snap_calls}"
