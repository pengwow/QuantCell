"""StrategyContext 新增字段测试。"""
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
