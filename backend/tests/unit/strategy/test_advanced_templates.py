"""3 高级策略模板冒烟测试。"""

from strategy.base import StrategyConfig, StrategyContext
from strategy.templates.cross_sectional import CrossSectional
from strategy.templates.funding_arbitrage import FundingArbitrage
from strategy.templates.mean_reversion_rl import MeanReversionRL


def _bars(prices: list[float], extra: dict | None = None) -> list[dict]:
    bars = [{"close": p, "open": p, "high": p, "low": p, "volume": 100.0} for p in prices]
    if extra:
        for b in bars:
            b.update(extra)
    return bars


# ---- FundingArbitrage ----


def test_funding_arbitrage_sell_on_positive_funding():
    """funding > 0 持续 N bar → 卖（做空吃费率）。"""
    s = FundingArbitrage(StrategyConfig(name="funding_arbitrage", params={"min_hold_bars": 3}))
    ctx = StrategyContext(symbol="BTCUSDT")
    actions = [s.on_bar({"close": 100.0, "funding_rate": 0.001, "timestamp": i}, ctx) for i in range(5)]
    assert any(str(a.action_type) == "sell" for a in actions), f"持续 5 bar funding > 0 应至少触发一次 sell: {actions}"


def test_funding_arbitrage_buy_on_negative_funding():
    """funding < 0 持续 N bar → 买（做多吃费率）。"""
    s = FundingArbitrage(StrategyConfig(name="funding_arbitrage", params={"min_hold_bars": 3}))
    ctx = StrategyContext(symbol="BTCUSDT")
    actions = [s.on_bar({"close": 100.0, "funding_rate": -0.001, "timestamp": i}, ctx) for i in range(5)]
    assert any(str(a.action_type) == "buy" for a in actions), f"持续 5 bar funding < 0 应至少触发一次 buy: {actions}"


def test_funding_arbitrage_hold_on_zero_funding():
    """funding ≈ 0 → 持仓不动（FLAT）。"""
    s = FundingArbitrage(StrategyConfig(name="funding_arbitrage"))
    ctx = StrategyContext(symbol="BTCUSDT")
    a = s.on_bar({"close": 100.0, "funding_rate": 0.0, "timestamp": 0}, ctx)
    assert str(a.action_type) == "hold"


# ---- CrossSectional ----


def test_cross_sectional_hold_while_warming_up():
    s = CrossSectional(StrategyConfig(name="cross_sectional", params={"lookback": 5}))
    ctx = StrategyContext(symbol="BTCUSDT")
    a = s.on_bar({"close": 100.0, "cross_sectional_rank": 1}, ctx)
    assert str(a.action_type) == "hold"


def test_cross_sectional_buy_top1_strong_momentum():
    """rank=1 + 强动量 → buy。"""
    s = CrossSectional(StrategyConfig(name="cross_sectional", params={"lookback": 5, "top_k": 1, "threshold": 0.1}))
    ctx = StrategyContext(symbol="BTCUSDT")
    # 5 根平 + 上涨 30%
    prices = [100.0] * 6 + [130.0]
    actions = [s.on_bar({"close": p, "cross_sectional_rank": 1}, ctx) for p in prices]
    assert any(str(a.action_type) == "buy" for a in actions), f"未触发 buy: {actions}"


def test_cross_sectional_hold_when_not_top1():
    """rank=0（不在 top_k）→ hold。"""
    s = CrossSectional(
        StrategyConfig(
            name="cross_sectional",
            params={"lookback": 5, "top_k": 1, "threshold": 0.05},
        )
    )
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
    s = MeanReversionRL(StrategyConfig(name="mean_reversion_rl", params={"bb_period": 10, "std_mult": 0.5}))
    ctx = StrategyContext(symbol="BTCUSDT")
    # 10 根稳定 + 大跌
    prices = [100.0] * 11 + [70.0]
    actions = [s.on_bar({"close": p}, ctx) for p in prices]
    assert any(str(a.action_type) == "buy" for a in actions), f"未触发 buy: {actions}"


def test_mean_reversion_rl_sell_on_overbought():
    """价格破上轨 → sell。"""
    s = MeanReversionRL(StrategyConfig(name="mean_reversion_rl", params={"bb_period": 10, "std_mult": 0.5}))
    ctx = StrategyContext(symbol="BTCUSDT")
    prices = [100.0] * 11 + [130.0]
    actions = [s.on_bar({"close": p}, ctx) for p in prices]
    assert any(str(a.action_type) == "sell" for a in actions), f"未触发 sell: {actions}"


# ---- FundingArbitrage 升级测试 ----


def test_funding_arbitrage_enters_long_funding_state():
    """FLAT + funding >= entry_threshold 持续 min_hold_bars bar → LONG_FUNDING 状态。

    验证：
    1. state 变量进入 LONG_FUNDING
    2. Action.target_position < 0（做空 perp）
    3. ctx.spot_target_position > 0（做多 spot）
    """
    from strategy.templates.funding_arbitrage import FundingState

    s = FundingArbitrage(
        StrategyConfig(
            name="funding_arbitrage",
            params={
                "entry_threshold": 0.0003,
                "min_hold_bars": 3,
                "target_position_pct": 0.1,
            },
        )
    )
    ctx = StrategyContext(symbol="BTCUSDT", account_equity=100000.0)
    for i in range(5):
        a = s.on_bar({"close": 50000.0, "funding_rate": 0.001, "timestamp": i}, ctx)
    assert s._state == FundingState.LONG_FUNDING, f"应进入 LONG_FUNDING, 实际 {s._state}"
    assert a.target_position < 0, f"perp 应做空, target={a.target_position}"
    assert ctx.spot_target_position > 0, f"spot 应做多, target={ctx.spot_target_position}"


def test_funding_arbitrage_exits_on_threshold_drop():
    """LONG_FUNDING + funding < exit_threshold → FLAT 状态。"""
    from strategy.templates.funding_arbitrage import FundingState

    s = FundingArbitrage(
        StrategyConfig(
            name="funding_arbitrage",
            params={
                "entry_threshold": 0.0003,
                "exit_threshold": 0.0001,
                "min_hold_bars": 2,
                "target_position_pct": 0.1,
            },
        )
    )
    ctx = StrategyContext(symbol="BTCUSDT", account_equity=100000.0)
    # 5 bar funding > entry → LONG_FUNDING
    for i in range(5):
        s.on_bar({"close": 50000.0, "funding_rate": 0.001, "timestamp": i}, ctx)
    assert s._state == FundingState.LONG_FUNDING
    # 1 bar funding 跌破 exit_threshold
    a = s.on_bar({"close": 50000.0, "funding_rate": 0.00005, "timestamp": 100}, ctx)
    assert s._state == FundingState.FLAT, f"应退到 FLAT, 实际 {s._state}"
    assert a.target_position == 0.0
    assert ctx.spot_target_position == 0.0


def test_funding_arbitrage_hold_counter_resets_on_noise():
    """funding 在 entry 上方持续 7 bar, 第 8 bar 跌破, 计数器 reset, 不入场。"""
    from strategy.templates.funding_arbitrage import FundingState

    s = FundingArbitrage(
        StrategyConfig(
            name="funding_arbitrage",
            params={
                "entry_threshold": 0.0003,
                "min_hold_bars": 8,
                "target_position_pct": 0.1,
            },
        )
    )
    ctx = StrategyContext(symbol="BTCUSDT", account_equity=100000.0)
    # 7 bar funding > entry
    for i in range(7):
        s.on_bar({"close": 50000.0, "funding_rate": 0.001, "timestamp": i}, ctx)
    # 第 8 bar 噪声
    s.on_bar({"close": 50000.0, "funding_rate": 0.0001, "timestamp": 7}, ctx)
    # 后续 funding 仍 > entry 但需要重数 8 bar
    for i in range(5):
        s.on_bar({"close": 50000.0, "funding_rate": 0.001, "timestamp": 100 + i}, ctx)
    # 状态应仍是 FLAT（5 bar 不够 min_hold_bars=8）
    assert s._state == FundingState.FLAT, f"噪声 reset 后只 5 bar, 应未入场, 实际 {s._state}"


# 注: test_funding_arbitrage_accumulates_funding_cash_on_long_funding 已删除
# 原因: 2026-07-18 axon_quant 0.6.0 升级后, funding cash 完全下沉到引擎的
# RunResult.total_funding_pnl, StrategyContext.settle_funding() 改为 no-op。
# 该测试验证"策略层累加 funding_cash" 的功能已不存在,删测试以匹配业务代码。


def test_funding_arbitrage_spot_leg_disabled_single_leg():
    """spot_leg_enabled=False → 现货目标=0, perp 仍动。"""
    s = FundingArbitrage(
        StrategyConfig(
            name="funding_arbitrage",
            params={
                "entry_threshold": 0.0003,
                "min_hold_bars": 2,
                "target_position_pct": 0.1,
                "spot_leg_enabled": False,
            },
        )
    )
    ctx = StrategyContext(symbol="BTCUSDT", account_equity=100000.0)
    for i in range(5):
        a = s.on_bar({"close": 50000.0, "funding_rate": 0.001, "timestamp": i}, ctx)
    from strategy.templates.funding_arbitrage import FundingState

    assert s._state == FundingState.LONG_FUNDING
    assert a.target_position < 0
    assert ctx.spot_target_position == 0.0


def test_funding_arbitrage_spot_margin_disabled_downgrades():
    """spot_margin_enabled=False + funding < -entry → SHORT_FUNDING 但 spot=0。"""
    s = FundingArbitrage(
        StrategyConfig(
            name="funding_arbitrage",
            params={
                "entry_threshold": 0.0003,
                "min_hold_bars": 2,
                "target_position_pct": 0.1,
                "spot_margin_enabled": False,
            },
        )
    )
    ctx = StrategyContext(symbol="BTCUSDT", account_equity=100000.0)
    for i in range(5):
        a = s.on_bar({"close": 50000.0, "funding_rate": -0.001, "timestamp": i}, ctx)
    from strategy.templates.funding_arbitrage import FundingState

    assert s._state == FundingState.SHORT_FUNDING
    assert a.target_position > 0
    assert ctx.spot_target_position == 0.0


def test_funding_arbitrage_reverses_to_short_funding():
    """LONG_FUNDING + funding 反号持续 N bar → 反转为 SHORT_FUNDING。"""
    s = FundingArbitrage(
        StrategyConfig(
            name="funding_arbitrage",
            params={
                "entry_threshold": 0.0003,
                "min_hold_bars": 2,
                "target_position_pct": 0.1,
                "spot_margin_enabled": True,
            },
        )
    )
    ctx = StrategyContext(symbol="BTCUSDT", account_equity=100000.0)
    for i in range(5):
        s.on_bar({"close": 50000.0, "funding_rate": 0.001, "timestamp": i}, ctx)
    from strategy.templates.funding_arbitrage import FundingState

    assert s._state == FundingState.LONG_FUNDING
    a = None
    for i in range(3):
        a = s.on_bar({"close": 50000.0, "funding_rate": -0.001, "timestamp": 100 + i}, ctx)
    assert s._state == FundingState.SHORT_FUNDING, f"应反转为 SHORT_FUNDING, 实际 {s._state}"
    assert a.target_position > 0
    assert ctx.spot_target_position < 0
