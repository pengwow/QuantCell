"""回测按标的参数覆盖（spec 2026-11-28 §5）。

monkeypatch loader 捕获逐标的解析调用：有覆盖 → 逐标的实例（参数各自合并）；
无覆盖 → 维持单一实例复用（与旧行为逐字段一致，回归守护）。
"""

import pandas as pd
import pytest
from pydantic import ValidationError

from backtest.engine_service import EventDrivenBacktestService
from backtest.schemas import StrategyConfig
from backtest.strategy_loader_service import StrategyLoaderService
from strategy.core import Action, ActionType


class _FakeStrategy:
    """BacktestLoop 只需 on_start/on_bar/on_stop；on_bar 恒 Hold"""

    def __init__(self):
        self.config = type("C", (), {"symbol": "BTCUSDT", "params": {}})()

    def on_start(self, ctx=None):
        pass

    def on_bar(self, bar, ctx=None):
        return Action(ActionType.Hold, 0.0, 0.0, "fake", 0)

    def on_stop(self, ctx=None):
        pass


def _df():
    idx = pd.date_range("2025-01-01", periods=5, freq="15min")
    return pd.DataFrame(
        {"open": [100.0] * 5, "high": [101.0] * 5, "low": [99.0] * 5, "close": [100.0] * 5, "volume": [10.0] * 5},
        index=idx,
    )


class _FakeProvider:
    def load_multiple(self, **kwargs):
        # kline 路径：{symbol_interval: df}
        return {
            "BTCUSDT_15m": _df(),
            "ETHUSDT_15m": _df(),
        }, None


def _capture_loader(monkeypatch):
    calls = []

    def fake_load(strategy_name, strategy_params, instrument_ids=None, bar_types=None, run_mode=None):
        calls.append((strategy_name, dict(strategy_params)))
        return _FakeStrategy()

    monkeypatch.setattr(StrategyLoaderService, "load_strategy", staticmethod(fake_load))
    return calls


def _run(monkeypatch, by_symbol, symbols, capital_mode="per_symbol"):
    calls = _capture_loader(monkeypatch)
    monkeypatch.setattr(EventDrivenBacktestService, "_load_funding", lambda self, *a, **k: None)
    svc = EventDrivenBacktestService(_FakeProvider())
    svc.run_backtest(
        strategy_name="grid",
        strategy_params={"levels": 20},
        strategy_params_by_symbol=by_symbol,
        symbols=symbols,
        timeframes=["15m"],
        engine_config={"runner": "python", "initial_cash": 10000.0, "capital_mode": capital_mode},
    )
    return calls


def test_per_symbol_loop_resolves_params_when_overrides_present(monkeypatch):
    """有覆盖：逐标的加载、参数 = 公共 + 覆盖；ETH 未覆盖 → 公共参数"""
    calls = _run(monkeypatch, {"BTCUSDT": {"lower": 80.0}}, ["BTCUSDT", "ETHUSDT"])
    assert len(calls) == 2
    params_seen = [params for _, params in calls]
    assert {"levels": 20, "lower": 80.0} in params_seen
    assert {"levels": 20} in params_seen


def test_shared_pool_resolves_params_per_symbol(monkeypatch):
    """spec §5：共享资金池路径同样逐标的解析（两路径都生效）"""
    calls = _run(monkeypatch, {"BTCUSDT": {"lower": 80.0}}, ["BTCUSDT", "ETHUSDT"], capital_mode="shared")
    params_seen = [params for _, params in calls]
    assert {"levels": 20, "lower": 80.0} in params_seen
    assert {"levels": 20} in params_seen


def test_per_symbol_loop_keeps_single_instance_without_overrides(monkeypatch):
    """无覆盖：维持单一实例（回归——与旧行为逐字段一致）"""
    calls = _run(monkeypatch, {}, ["BTCUSDT", "ETHUSDT"])
    assert len(calls) == 1
    assert calls[0][1] == {"levels": 20}


def test_backtest_strategy_config_accepts_by_symbol():
    cfg = StrategyConfig(strategy_name="grid", params={}, strategy_params_by_symbol={"BTCUSDT": {"lower": 1.0}})
    assert cfg.strategy_params_by_symbol == {"BTCUSDT": {"lower": 1.0}}


def test_backtest_strategy_config_defaults_by_symbol_none():
    assert StrategyConfig(strategy_name="grid").strategy_params_by_symbol is None
