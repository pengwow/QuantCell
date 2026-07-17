"""StrategyContext 新增字段测试。"""
import math

import pytest
from strategy.base import StrategyContext


def test_strategy_context_has_funding_cash_field():
    """新字段 funding_cash 默认 0.0。"""
    ctx = StrategyContext(symbol="BTCUSDT")
    assert hasattr(ctx, "funding_cash")
    assert ctx.funding_cash == 0.0


def test_strategy_context_has_spot_fields():
    """新字段 spot_symbol/spot_close/spot_volume 默认空。"""
    ctx = StrategyContext(symbol="BTCUSDT")
    assert hasattr(ctx, "spot_symbol")
    assert ctx.spot_symbol == ""
    assert hasattr(ctx, "spot_close")
    assert ctx.spot_close == 0.0
    assert hasattr(ctx, "spot_volume")
    assert ctx.spot_volume == 0.0


def test_strategy_context_has_spot_target_position():
    """新字段 spot_target_position 默认 0.0。"""
    ctx = StrategyContext(symbol="BTCUSDT")
    assert hasattr(ctx, "spot_target_position")
    assert ctx.spot_target_position == 0.0


def test_strategy_context_has_funding_metadata():
    """新字段 last_funding_rate / last_funding_time 默认 0。"""
    ctx = StrategyContext(symbol="BTCUSDT")
    assert ctx.last_funding_rate == 0.0
    assert ctx.last_funding_time == 0


def test_strategy_context_has_settle_funding_method():
    """新方法 settle_funding 存在。"""
    ctx = StrategyContext(symbol="BTCUSDT")
    assert hasattr(ctx, "settle_funding")
    assert callable(ctx.settle_funding)


def test_legacy_context_construction_still_works():
    """老构造方式（仅 symbol）仍工作 — 兼容性。"""
    ctx = StrategyContext(symbol="BTCUSDT")
    assert ctx.symbol == "BTCUSDT"
    assert ctx.closes == []
    assert ctx.positions == {}
    assert ctx.orders == []


def test_settle_funding_basic_long_position_pays():
    """持仓多头 + funding > 0 → 付出 funding（cash_delta < 0）。"""
    ctx = StrategyContext(symbol="BTCUSDT")
    delta = ctx.settle_funding(
        funding_rate=0.0003, funding_time=1000, position_notional=50000.0
    )
    assert delta == pytest.approx(-15.0, rel=1e-6)  # -0.0003 × 50000
    assert ctx.funding_cash == pytest.approx(-15.0, rel=1e-6)
    assert ctx.last_funding_rate == 0.0003
    assert ctx.last_funding_time == 1000


def test_settle_funding_basic_short_position_receives():
    """持仓空头 + funding > 0 → 收入 funding（cash_delta > 0）。

    约定：position_notional 是当前持仓名义价值（USD）。
    实际策略中, funding cash 与持仓符号方向相反:
        多头 + funding > 0 → 付出
        空头 + funding > 0 → 收入
    因此本测试传入负的 notional 模拟空头, 验证 cash > 0
    """
    ctx = StrategyContext(symbol="BTCUSDT")
    delta = ctx.settle_funding(
        funding_rate=0.0003, funding_time=1000, position_notional=-50000.0
    )
    assert delta == pytest.approx(+15.0, rel=1e-6)  # -0.0003 × (-50000)
    assert ctx.funding_cash == pytest.approx(+15.0, rel=1e-6)


def test_settle_funding_skips_duplicate_time():
    """funding_time <= last_funding_time → 跳过累加（重复事件防御）。"""
    ctx = StrategyContext(symbol="BTCUSDT")
    ctx.settle_funding(funding_rate=0.0003, funding_time=1000, position_notional=50000.0)
    delta2 = ctx.settle_funding(funding_rate=0.0005, funding_time=1000, position_notional=50000.0)
    assert delta2 == 0.0
    assert ctx.funding_cash == pytest.approx(-15.0, rel=1e-6)  # 仍是第一次
    assert ctx.last_funding_time == 1000


def test_settle_funding_skips_nan():
    """funding_rate 是 NaN/Inf → 跳过累加, 不污染 funding_cash。"""
    ctx = StrategyContext(symbol="BTCUSDT")
    delta = ctx.settle_funding(
        funding_rate=float("nan"), funding_time=1000, position_notional=50000.0
    )
    assert delta == 0.0
    assert ctx.funding_cash == 0.0
    assert ctx.last_funding_time == 0  # 未更新


def test_settle_funding_skips_when_disabled():
    """funding_cash_settlement_enabled=False → 跳过累加（调试模式）。"""
    ctx = StrategyContext(symbol="BTCUSDT", funding_cash_settlement_enabled=False)
    delta = ctx.settle_funding(
        funding_rate=0.0003, funding_time=1000, position_notional=50000.0
    )
    assert delta == 0.0
    assert ctx.funding_cash == 0.0


def test_settle_funding_accumulates_multiple_events():
    """多次累加：funding_cash 累加正确。"""
    ctx = StrategyContext(symbol="BTCUSDT")
    ctx.settle_funding(funding_rate=0.0001, funding_time=1000, position_notional=50000.0)
    ctx.settle_funding(funding_rate=0.0003, funding_time=2000, position_notional=50000.0)
    ctx.settle_funding(funding_rate=0.0005, funding_time=3000, position_notional=50000.0)
    expected = -(0.0001 + 0.0003 + 0.0005) * 50000  # = -45
    assert ctx.funding_cash == pytest.approx(expected, rel=1e-6)
