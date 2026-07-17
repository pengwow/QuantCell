"""3 高级策略模板冒烟测试。"""
import pytest

from strategy.base import StrategyConfig, StrategyContext
from strategy.templates.funding_arbitrage import FundingArbitrage
from strategy.templates.cross_sectional import CrossSectional
from strategy.templates.mean_reversion_rl import MeanReversionRL


def _bars(prices: list[float], extra: dict | None = None) -> list[dict]:
    bars = [{"close": p, "open": p, "high": p, "low": p, "volume": 100.0} for p in prices]
    if extra:
        for b in bars:
            b.update(extra)
    return bars


# ---- FundingArbitrage ----

def test_funding_arbitrage_sell_on_positive_funding():
    """funding > 0 → 卖（做空吃费率）。"""
    s = FundingArbitrage(StrategyConfig(name="funding_arbitrage"))
    ctx = StrategyContext(symbol="BTCUSDT")
    a = s.on_bar({"close": 100.0, "funding_rate": 0.001}, ctx)
    assert str(a.action_type) == "sell"


def test_funding_arbitrage_buy_on_negative_funding():
    """funding < 0 → 买（做多吃费率）。"""
    s = FundingArbitrage(StrategyConfig(name="funding_arbitrage"))
    ctx = StrategyContext(symbol="BTCUSDT")
    a = s.on_bar({"close": 100.0, "funding_rate": -0.001}, ctx)
    assert str(a.action_type) == "buy"


def test_funding_arbitrage_hold_on_zero_funding():
    """funding ≈ 0 → 持仓不动。"""
    s = FundingArbitrage(StrategyConfig(name="funding_arbitrage"))
    ctx = StrategyContext(symbol="BTCUSDT")
    a = s.on_bar({"close": 100.0, "funding_rate": 0.0}, ctx)
    assert str(a.action_type) == "hold"


# ---- CrossSectional ----

def test_cross_sectional_hold_while_warming_up():
    s = CrossSectional(StrategyConfig(name="cross_sectional", params={"lookback": 5}))
    ctx = StrategyContext(symbol="BTCUSDT")
    a = s.on_bar({"close": 100.0, "cross_sectional_rank": 1}, ctx)
    assert str(a.action_type) == "hold"


def test_cross_sectional_buy_top1_strong_momentum():
    """rank=1 + 强动量 → buy。"""
    s = CrossSectional(StrategyConfig(name="cross_sectional",
                                      params={"lookback": 5, "top_k": 1, "threshold": 0.1}))
    ctx = StrategyContext(symbol="BTCUSDT")
    # 5 根平 + 上涨 30%
    prices = [100.0] * 6 + [130.0]
    actions = [s.on_bar({"close": p, "cross_sectional_rank": 1}, ctx) for p in prices]
    assert any(str(a.action_type) == "buy" for a in actions), f"未触发 buy: {actions}"


def test_cross_sectional_hold_when_not_top1():
    """rank=0（不在 top_k）→ hold。"""
    s = CrossSectional(StrategyConfig(name="cross_sectional",
                                      params={"lookback": 5, "top_k": 1, "threshold": 0.05}))
    ctx = StrategyContext(symbol="BTCUSDT")
    prices = [100.0] * 6 + [200.0]
    actions = [s.on_bar({"close": p, "cross_sectional_rank": 0}, ctx) for p in prices]
    assert not any(str(a.action_type) == "buy" for a in actions), f"不应触发 buy: {actions}"


# ---- MeanReversionRL ----

def test_mean_reversion_rl_hold_while_warming_up():
    s = MeanReversionRL(StrategyConfig(name="mean_reversion_rl", params={"bb_period": 5}))
    ctx = StrategyContext(symbol="BTCUSDT")
    a = s.on_bar({"close": 100.0}, ctx)
    assert str(a.action_type) == "hold"


def test_mean_reversion_rl_buy_on_oversold_low_vol():
    """价格破下轨 + 低波动 → buy。"""
    s = MeanReversionRL(StrategyConfig(name="mean_reversion_rl",
                                        params={"bb_period": 10, "std_mult": 0.5}))
    ctx = StrategyContext(symbol="BTCUSDT")
    # 10 根稳定 + 大跌
    prices = [100.0] * 11 + [70.0]
    actions = [s.on_bar({"close": p}, ctx) for p in prices]
    assert any(str(a.action_type) == "buy" for a in actions), f"未触发 buy: {actions}"


def test_mean_reversion_rl_sell_on_overbought():
    """价格破上轨 → sell。"""
    s = MeanReversionRL(StrategyConfig(name="mean_reversion_rl",
                                        params={"bb_period": 10, "std_mult": 0.5}))
    ctx = StrategyContext(symbol="BTCUSDT")
    prices = [100.0] * 11 + [130.0]
    actions = [s.on_bar({"close": p}, ctx) for p in prices]
    assert any(str(a.action_type) == "sell" for a in actions), f"未触发 sell: {actions}"
