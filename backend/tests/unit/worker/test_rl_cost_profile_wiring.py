"""RL paper/live 内核费率必须与训练产物 meta 同源。

守两件事：meta 记录了训练时的 cost profile 费率 → 内核拿到该值；
旧模型 meta 无 `transaction_cost` → 回落 `RL_TRANSACTION_COST`（零漂移）。
"""

import json
import threading
from pathlib import Path

import pytest

from services.rl_service import RL_TRANSACTION_COST


def _write_model_with_meta(tmp_path: Path, *, transaction_cost: float | None = None) -> Path:
    model_path = tmp_path / "demo_ppo.zip"
    model_path.write_bytes(b"fake-sb3-model")
    meta = {"model_id": "demo_ppo", "spec_version": "v1", "window_size": 1}
    if transaction_cost is not None:
        meta["transaction_cost"] = transaction_cost
    Path(f"{model_path}.meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return model_path


def test_build_rl_kernel_uses_meta_transaction_cost(monkeypatch, tmp_path):
    axon_quant = pytest.importorskip("axon_quant")
    if not hasattr(axon_quant, "worker"):
        pytest.skip("axon_quant.worker 不可用")

    from worker.strategy_manager import StrategyManager

    model_path = _write_model_with_meta(tmp_path, transaction_cost=5e-4)
    registered: dict[str, object] = {}

    class FakeKernel:
        def __init__(self, **kwargs):
            registered["init"] = kwargs

        def add_rl_strategy(self, *args, **kwargs):
            pass

    monkeypatch.setattr(axon_quant.worker, "Kernel", FakeKernel)
    monkeypatch.setattr("services.rl_service.RLService.load_model", lambda self, path: object())

    mgr = StrategyManager(max_workers=1)
    try:
        mgr.build_rl_kernel(1, {"model_path": str(model_path)}, "1h", ["BTCUSDT"])
    finally:
        mgr.shutdown()

    assert registered["init"]["fee_rate"] == 5e-4


def test_build_rl_kernel_falls_back_to_constant_without_meta_field(monkeypatch, tmp_path):
    axon_quant = pytest.importorskip("axon_quant")
    if not hasattr(axon_quant, "worker"):
        pytest.skip("axon_quant.worker 不可用")

    from worker.strategy_manager import StrategyManager

    model_path = _write_model_with_meta(tmp_path)  # 旧 meta：无 transaction_cost
    registered: dict[str, object] = {}

    class FakeKernel:
        def __init__(self, **kwargs):
            registered["init"] = kwargs

        def add_rl_strategy(self, *args, **kwargs):
            pass

    monkeypatch.setattr(axon_quant.worker, "Kernel", FakeKernel)
    monkeypatch.setattr("services.rl_service.RLService.load_model", lambda self, path: object())

    mgr = StrategyManager(max_workers=1)
    try:
        mgr.build_rl_kernel(2, {"model_path": str(model_path)}, "1h", ["BTCUSDT"])
    finally:
        mgr.shutdown()

    assert registered["init"]["fee_rate"] == RL_TRANSACTION_COST


def test_start_rl_paper_driver_gets_meta_transaction_cost(monkeypatch, tmp_path):
    """模拟盘装配点：PaperDriver 的 fee_rate 取 meta 值，不是常量。"""
    axon_quant = pytest.importorskip("axon_quant")
    if not hasattr(axon_quant, "worker"):
        pytest.skip("axon_quant.worker 不可用")

    from worker.state import StrategyRuntime, strategy_registry
    from worker.strategy_manager import StrategyManager

    model_path = _write_model_with_meta(tmp_path, transaction_cost=3e-4)
    calls: dict[str, object] = {}
    first_round_done = threading.Event()

    class FakePaperDriver:
        def __init__(self, symbols, **kwargs):
            calls["init"] = kwargs

        def add_rl_strategy(self, *args, **kwargs):
            pass

        def start(self):
            pass

        def feed_bar(self, *args):
            pass

        def tick(self):
            first_round_done.set()

        def shutdown(self):
            pass

    monkeypatch.setattr(axon_quant.worker, "PaperDriver", FakePaperDriver)
    monkeypatch.setattr("services.rl_service.RLService.load_model", lambda self, path: object())
    monkeypatch.setattr(StrategyManager, "_paper_fetch_klines", lambda self, *args, **kwargs: [])

    runtime = StrategyRuntime(worker_id=11, strategy_id=0, name="rl-paper-fee", status="starting")
    strategy_registry.register(runtime)
    mgr = StrategyManager(max_workers=1)
    try:
        mgr.start_rl_paper(11, {"model_path": str(model_path)}, "1h", ["BTCUSDT"], "binance", "swap")
        assert calls["init"]["fee_rate"] == 3e-4
        assert first_round_done.wait(timeout=10)
    finally:
        live = mgr._kernel_runs.pop(11, None)
        if live is not None:
            live["stop_event"].set()
            live["thread"].join(timeout=5)
        mgr.shutdown()
        strategy_registry.unregister(11)
