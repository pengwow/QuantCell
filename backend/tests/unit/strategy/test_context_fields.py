"""StrategyContext 新增字段测试。"""

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
    """DEPRECATED: 策略层不再累加 funding_cash (2026-07-18 0.6.0 升级后下沉到 axon_quant 引擎)。
    settle_funding 已改为 no-op, 无论参数如何都返回 0.0, funding_cash 不变。
    """
    ctx = StrategyContext(symbol="BTCUSDT")
    delta = ctx.settle_funding(funding_rate=0.0003, funding_time=1000, position_notional=50000.0)
    assert delta == 0.0
    assert ctx.funding_cash == 0.0
    assert ctx.last_funding_rate == 0.0
    assert ctx.last_funding_time == 0


def test_settle_funding_basic_short_position_receives():
    """DEPRECATED: 策略层不再累加 funding_cash。
    no-op 行为: 无论 long/short 持仓, settle_funding 都返回 0.0, funding_cash 不变。
    """
    ctx = StrategyContext(symbol="BTCUSDT")
    delta = ctx.settle_funding(funding_rate=0.0003, funding_time=1000, position_notional=-50000.0)
    assert delta == 0.0
    assert ctx.funding_cash == 0.0


def test_settle_funding_skips_duplicate_time():
    """DEPRECATED: 重复时间防御已下沉到 PushFundingHelper (axon_bridge.backtest)。
    no-op 行为: settle_funding 始终返回 0.0, 无累加。
    """
    ctx = StrategyContext(symbol="BTCUSDT")
    ctx.settle_funding(funding_rate=0.0003, funding_time=1000, position_notional=50000.0)
    delta2 = ctx.settle_funding(funding_rate=0.0005, funding_time=1000, position_notional=50000.0)
    assert delta2 == 0.0
    assert ctx.funding_cash == 0.0
    assert ctx.last_funding_time == 0


def test_settle_funding_skips_nan():
    """no-op 行为: 即使 funding_rate 是 NaN, settle_funding 也返回 0.0。
    NaN 防御已下沉到 axon_quant 引擎 (RunResult.total_funding_pnl 在引擎层有 sanity check)。
    """
    ctx = StrategyContext(symbol="BTCUSDT")
    delta = ctx.settle_funding(funding_rate=float("nan"), funding_time=1000, position_notional=50000.0)
    assert delta == 0.0
    assert ctx.funding_cash == 0.0
    assert ctx.last_funding_time == 0  # 未更新


def test_settle_funding_skips_when_disabled():
    """no-op 行为: funding_cash_settlement_enabled=False 时(且默认也是 False)也返回 0.0。"""
    ctx = StrategyContext(symbol="BTCUSDT", funding_cash_settlement_enabled=False)
    delta = ctx.settle_funding(funding_rate=0.0003, funding_time=1000, position_notional=50000.0)
    assert delta == 0.0
    assert ctx.funding_cash == 0.0


def test_settle_funding_accumulates_multiple_events():
    """DEPRECATED: 多次累加 funding_cash 已下沉到 axon_quant 引擎的 total_funding_pnl。
    no-op 行为: 多次调用 settle_funding 累加为 0, funding_cash 始终为 0.0。
    """
    ctx = StrategyContext(symbol="BTCUSDT")
    ctx.settle_funding(funding_rate=0.0001, funding_time=1000, position_notional=50000.0)
    ctx.settle_funding(funding_rate=0.0003, funding_time=2000, position_notional=50000.0)
    ctx.settle_funding(funding_rate=0.0005, funding_time=3000, position_notional=50000.0)
    assert ctx.funding_cash == 0.0
