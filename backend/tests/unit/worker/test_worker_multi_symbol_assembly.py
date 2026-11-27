"""Worker 多标的逐标的装配（spec 2026-11-28 §4.1 D2）。

只锁装配公约（不测泵线程）：PaperDriver/LiveDriver 每个标的各挂一个独立
RustStrategyAdapter；资金/风控仍取公共参数。
"""

import types

from worker.strategy_manager import StrategyManager


class _FakeStrategy:
    """最小策略桩：RustStrategyAdapter 需要 config.symbol 与 on_start"""

    def __init__(self, symbol="BTCUSDT"):
        self.config = types.SimpleNamespace(symbol=symbol, params={})

    def on_start(self, ctx=None):
        pass


class _FakeDriver:
    def __init__(self, symbols, initial_cash=0.0, interval=None, **kwargs):
        self.symbols = symbols
        self.initial_cash = initial_cash
        self.added = []  # (adapter, symbol)

    def add_strategy(self, strategy, name=None, symbol=None):
        self.added.append((strategy, symbol))

    def set_risk_config(self, *args, **kwargs):
        pass


def test_paper_driver_mounts_one_adapter_per_symbol(monkeypatch):
    """D2：两标的 → add_strategy 两次、symbol 为 expand_symbol 形态、adapter 身份互不相同"""
    # 注意：`import axon_quant.worker` 会 ModuleNotFoundError（worker 是 __init__ 里
    # 懒暴露的子模块，未注册 sys.modules['axon_quant.worker']），必须走 from 导入，
    # 与 _assemble_rule_paper_driver 内部的 `from axon_quant import worker` 同源。
    from axon_quant import worker as axon_worker

    monkeypatch.setattr(axon_worker, "PaperDriver", _FakeDriver)
    monkeypatch.setattr("worker.strategy_manager.apply_risk_config", lambda *a, **k: False)

    instances = {"BTCUSDT": _FakeStrategy("BTCUSDT"), "ETHUSDT": _FakeStrategy("ETHUSDT")}
    driver, risk_enabled = StrategyManager()._assemble_rule_paper_driver(
        1, instances, {"initial_capital": 10000.0}, "1m", ["BTCUSDT", "ETHUSDT"]
    )

    assert len(driver.added) == 2
    assert [sym for _, sym in driver.added] == ["BTC/USDT", "ETH/USDT"]
    assert driver.added[0][0] is not driver.added[1][0]
    assert driver.initial_cash == 10000.0  # 资金取公共参数
    assert risk_enabled is False
