"""factor_timing 因子择时模板测试。"""

import pytest

from axon_bridge import Action
from strategy.base import StrategyConfig, StrategyContext
from strategy.templates.factor_timing import FactorTiming


def _ctx() -> StrategyContext:
    return StrategyContext(symbol="BTCUSDT")


def _bar(close: float = 100.0) -> dict:
    return {"close": close, "timestamp_ns": 0}


def test_hold_when_factor_missing():
    s = FactorTiming(StrategyConfig(name="factor_timing", params={"factor_name": "momentum_5d"}))
    ctx = _ctx()
    action = s.on_bar(_bar(), ctx)
    assert str(action.action_type) == "hold"


def test_buy_when_factor_above_buy_threshold():
    s = FactorTiming(
        StrategyConfig(
            name="factor_timing",
            position_limit=0.2,
            params={"factor_name": "momentum_5d", "buy_threshold": 0.05, "sell_threshold": -0.05},
        )
    )
    ctx = _ctx()
    ctx.features["momentum_5d"] = 0.08
    action = s.on_bar(_bar(), ctx)
    assert str(action.action_type) == "buy"
    # axon_quant 0.14.x 的原生 Action 以 f32 存储 target_position，0.2 回读为
    # 0.20000000298023224，无法与 f64 字面量精确相等，故用 approx 比较
    assert action.target_position == pytest.approx(0.2)


def test_sell_when_factor_below_sell_threshold():
    s = FactorTiming(
        StrategyConfig(
            name="factor_timing", params={"factor_name": "momentum_5d", "buy_threshold": 0.05, "sell_threshold": -0.05}
        )
    )
    ctx = _ctx()
    ctx.features["momentum_5d"] = -0.1
    action = s.on_bar(_bar(), ctx)
    assert str(action.action_type) == "sell"
    assert action.target_position == 0.0


def test_hold_in_middle_band():
    s = FactorTiming(
        StrategyConfig(
            name="factor_timing", params={"factor_name": "momentum_5d", "buy_threshold": 0.05, "sell_threshold": -0.05}
        )
    )
    ctx = _ctx()
    ctx.features["momentum_5d"] = 0.0
    assert str(s.on_bar(_bar(), ctx).action_type) == "hold"


def test_threshold_boundary_is_inclusive():
    s = FactorTiming(
        StrategyConfig(
            name="factor_timing", params={"factor_name": "momentum_5d", "buy_threshold": 0.05, "sell_threshold": -0.05}
        )
    )
    ctx = _ctx()
    ctx.features["momentum_5d"] = 0.05
    assert str(s.on_bar(_bar(), ctx).action_type) == "buy"
