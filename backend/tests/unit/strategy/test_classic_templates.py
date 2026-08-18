"""4 经典策略模板冒烟测试。"""

from strategy.base import StrategyConfig, StrategyContext
from strategy.templates.grid import Grid
from strategy.templates.mean_reversion import MeanReversion
from strategy.templates.momentum import Momentum
from strategy.templates.trend_follow import TrendFollow


def _bars(prices: list[float]) -> list[dict]:
    return [{"close": p, "open": p, "high": p, "low": p, "volume": 100.0} for p in prices]


# ---- TrendFollow ----


def test_trend_follow_hold_while_warming_up():
    s = TrendFollow(StrategyConfig(name="trend_follow", params={"lookback": 5, "atr_period": 3}))
    ctx = StrategyContext(symbol="BTCUSDT")
    for bar in _bars([100.0] * 4):
        a = s.on_bar(bar, ctx)
        assert str(a.action_type) == "hold"


def test_trend_follow_buy_on_breakout():
    s = TrendFollow(
        StrategyConfig(
            name="trend_follow",
            params={"lookback": 5, "atr_period": 3, "atr_mult": 5.0},
        )
    )
    ctx = StrategyContext(symbol="BTCUSDT")
    # 5 根横盘 + 突破大涨
    prices = [100.0] * 6 + [200.0]
    actions = [s.on_bar(bar, ctx) for bar in _bars(prices)]
    assert any(str(a.action_type) == "buy" for a in actions), f"未触发 buy: {actions}"


# ---- Grid ----


def test_grid_hold_in_range():
    s = Grid(StrategyConfig(name="grid", params={"lower": 90.0, "upper": 110.0, "levels": 10}))
    ctx = StrategyContext(symbol="BTCUSDT")
    a = s.on_bar({"close": 100.0}, ctx)
    assert str(a.action_type) == "hold"


def test_grid_buy_on_drop():
    s = Grid(StrategyConfig(name="grid", params={"lower": 90.0, "upper": 110.0, "levels": 10}))
    ctx = StrategyContext(symbol="BTCUSDT")
    # 价格跌 → 触发 buy
    s.on_bar({"close": 100.0}, ctx)  # 100 → idx=5
    a = s.on_bar({"close": 95.0}, ctx)  # 95 → idx=2
    assert str(a.action_type) == "buy"


# ---- MeanReversion ----


def test_mean_reversion_hold_no_signal():
    s = MeanReversion(StrategyConfig(name="mean_reversion", params={"bb_period": 5, "rsi_period": 5}))
    ctx = StrategyContext(symbol="BTCUSDT")
    for bar in _bars([100.0] * 10):
        a = s.on_bar(bar, ctx)
        assert str(a.action_type) == "hold"


def test_mean_reversion_buy_on_oversold():
    s = MeanReversion(
        StrategyConfig(
            name="mean_reversion",
            params={"bb_period": 5, "rsi_period": 5, "std_mult": 0.5},
        )
    )
    ctx = StrategyContext(symbol="BTCUSDT")
    # 横盘后暴跌 → 触发 buy
    prices = [100.0] * 6 + [50.0, 50.0, 50.0, 50.0, 50.0, 50.0]
    actions = [s.on_bar(bar, ctx) for bar in _bars(prices)]
    assert any(str(a.action_type) == "buy" for a in actions), f"未触发 buy: {actions}"


# ---- Momentum ----


def test_momentum_hold_no_big_move():
    s = Momentum(StrategyConfig(name="momentum", params={"lookback": 5, "threshold": 0.1}))
    ctx = StrategyContext(symbol="BTCUSDT")
    for bar in _bars([100.0] * 10):
        a = s.on_bar(bar, ctx)
        assert str(a.action_type) == "hold"


def test_momentum_buy_on_strong_up():
    s = Momentum(StrategyConfig(name="momentum", params={"lookback": 5, "threshold": 0.1}))
    ctx = StrategyContext(symbol="BTCUSDT")
    # 5 根平 → 上涨 20%
    prices = [100.0] * 6 + [120.0]
    actions = [s.on_bar(bar, ctx) for bar in _bars(prices)]
    assert any(str(a.action_type) == "buy" for a in actions), f"未触发 buy: {actions}"
