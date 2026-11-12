"""P2-10：wire 事件 schema_version 注入检查。

三个组装点中 worker_event 信封在 core/lifespan.py 的事件循环里内联构造，
依赖 FastAPI 生命周期无法单测；这里覆盖 strategy_event 与 kernel.snapshot
两个可直测点，worker_event 靠同一常量与前端 migrate_event 门兜底。
"""

import asyncio

from worker import state as worker_state
from worker.events import EVENTS_SCHEMA_VERSION
from worker.strategy_manager import StrategyManager


def test_strategy_event_carries_schema_version(monkeypatch):
    captured: dict = {}

    class FakeManager:
        @staticmethod
        async def broadcast(message):
            captured.update(message)

    monkeypatch.setattr(worker_state, "connection_manager", FakeManager())

    async def scenario():
        worker_state._broadcast_state_change(1, "running", "stopped", None)
        await asyncio.sleep(0)  # 放行 create_task 排程的 broadcast

    asyncio.run(scenario())
    assert captured["type"] == "strategy_event"
    assert captured["schema_version"] == EVENTS_SCHEMA_VERSION


def test_kernel_snapshot_carries_schema_version(monkeypatch):
    captured: dict = {}

    class FakeCM:
        @staticmethod
        def broadcast_threadsafe(message):
            captured.update(message)

    monkeypatch.setattr(worker_state, "connection_manager", FakeCM())

    StrategyManager._push_kernel_snapshot(1, {"equity": 100.0, "positions": []})
    assert captured["event"] == "kernel.snapshot"
    assert captured["schema_version"] == EVENTS_SCHEMA_VERSION
