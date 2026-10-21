"""RustStrategyAdapter 杠杆换算单测：杠杆只在 Python 侧乘一次。

Rust 引擎收到的是绝对数量；若这里之外再乘，会变成 leverage²。
"""

from __future__ import annotations

import pytest

from axon_bridge import Action
from strategy.base import BaseStrategy, StrategyConfig
from strategy.rust_adapter import RustStrategyAdapter


class _AlwaysBuy(BaseStrategy):
    def __init__(self):
        super().__init__(StrategyConfig(name="always_buy", symbol="BTCUSDT", params={}))

    def on_bar(self, bar, ctx):
        # ActionType 是 pyo3 暴露的类属性而非 str 枚举，构造 Action 需传字符串
        return Action(
            action_type="buy", confidence=1.0, target_position=0.1, model_id="always_buy", inference_time_us=0
        )


def _decide(leverage: float) -> float:
    adapter = RustStrategyAdapter(_AlwaysBuy(), initial_cash=10_000.0, symbol="BTCUSDT", leverage=leverage)
    out = adapter.decide({"close": 100.0, "open": 100.0, "high": 100.0, "low": 100.0, "volume": 1.0})
    return out["target_position"]


def test_leverage_multiplies_target_once():
    # ratio 0.1 × 10000 / 100 = 10 张；10x → 100 张（乘两次会得到 1000）。
    # Action.target_position 是 pyo3 f32 字段（0.1 会带 1e-7 级误差），故用近似断言。
    assert _decide(1.0) == pytest.approx(10.0, rel=1e-6)
    assert _decide(10.0) == pytest.approx(100.0, rel=1e-6)


def test_default_leverage_keeps_parity():
    assert _decide(1.0) == pytest.approx(10.0, rel=1e-6)
