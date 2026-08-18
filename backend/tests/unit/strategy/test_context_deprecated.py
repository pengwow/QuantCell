"""StrategyContext.funding_cash/settle_funding 标 DEPRECATED no-op。"""

from strategy.base import StrategyContext


def test_funding_cash_default_zero():
    """funding_cash 默认 0 (no-op 字段)。"""
    ctx = StrategyContext(symbol="BTCUSDT")
    assert ctx.funding_cash == 0.0


def test_settle_funding_returns_zero():
    """settle_funding 标 no-op, 返回 0.0 (无论参数如何)。"""
    ctx = StrategyContext(symbol="BTCUSDT")
    cash = ctx.settle_funding(
        funding_rate=0.0003,
        funding_time=1234567890,
        position_notional=10000.0,
    )
    assert cash == 0.0


def test_settle_funding_does_not_mutate_funding_cash():
    """settle_funding 不修改 funding_cash。"""
    ctx = StrategyContext(symbol="BTCUSDT")
    ctx.settle_funding(
        funding_rate=0.0003,
        funding_time=1234567890,
        position_notional=10000.0,
    )
    assert ctx.funding_cash == 0.0


def test_funding_cash_settlement_enabled_default_false():
    """funding_cash_settlement_enabled 默认 False (防止意外累加)。"""
    ctx = StrategyContext(symbol="BTCUSDT")
    assert ctx.funding_cash_settlement_enabled is False
