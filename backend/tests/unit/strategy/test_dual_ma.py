"""8 策略模板冒烟测试。"""
import pytest

from strategy.base import StrategyConfig, StrategyContext
from strategy.templates.dual_ma import DualMA


def _gen_prices(trend: list[float]) -> list[dict]:
    return [{"close": p, "open": p, "high": p, "low": p, "volume": 100.0} for p in trend]


def test_dual_ma_hold_while_warming_up():
    """前 slow 根 K 线返回 hold。"""
    s = DualMA(StrategyConfig(name="dual_ma", params={"fast": 5, "slow": 10}))
    ctx = StrategyContext(symbol="BTCUSDT")
    for bar in _gen_prices([100.0] * 9):
        a = s.on_bar(bar, ctx)
        assert str(a.action_type) == "hold"
    assert len(ctx.closes) == 9


def test_dual_ma_buy_on_golden_cross():
    """金叉（快线从下方穿越慢线）→ buy。"""
    s = DualMA(StrategyConfig(name="dual_ma", params={"fast": 3, "slow": 5}))
    ctx = StrategyContext(symbol="BTCUSDT")
    # 前 5 根横盘 → 第 6 根起上涨 → 触发金叉
    prices = [100.0] * 6 + [110.0, 120.0, 130.0]
    actions = [s.on_bar(bar, ctx) for bar in _gen_prices(prices)]
    assert any(str(a.action_type) == "buy" for a in actions), f"未触发 buy: {actions}"


def test_dual_ma_sell_on_death_cross():
    """死叉（快线从上方穿越慢线）→ sell。"""
    s = DualMA(StrategyConfig(name="dual_ma", params={"fast": 3, "slow": 5}))
    ctx = StrategyContext(symbol="BTCUSDT")
    # 先涨后跌 → 触发死叉
    prices = [100.0] * 4 + [120.0, 130.0, 140.0, 150.0, 100.0, 80.0, 60.0]
    actions = [s.on_bar(bar, ctx) for bar in _gen_prices(prices)]
    assert any(str(a.action_type) == "sell" for a in actions), f"未触发 sell: {actions}"


def test_dual_ma_first_bar_no_signal():
    """首次 K 线仅记录状态，不立即下单。"""
    s = DualMA(StrategyConfig(name="dual_ma", params={"fast": 3, "slow": 5}))
    ctx = StrategyContext(symbol="BTCUSDT")
    a = s.on_bar({"close": 100.0}, ctx)
    assert str(a.action_type) == "hold"
