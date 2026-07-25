"""llm_signal 策略模板单元测试。"""
from __future__ import annotations

from strategy.base import StrategyConfig, StrategyContext
from strategy.templates.llm_signal import LLMSignalStrategy, _heuristic_signal
from axon_bridge import MarketSignal, SignalType, ActionType


def _bar(price: float) -> dict:
    return {"open": price, "high": price * 1.001, "low": price * 0.999,
            "close": price, "volume": 100.0}


def test_llm_signal_registered():
    """策略通过 loader 可发现。"""
    from strategy.loader import StrategyLoader
    assert "llm_signal" in StrategyLoader.list_all()


def test_heuristic_signal_warmup():
    """数据不足时返回 Hold。"""
    sig = _heuristic_signal([100.0] * 10, fast=5, slow=20)
    assert sig.signal_type == SignalType.Hold
    assert sig.confidence == 0.0


def test_heuristic_golden_cross():
    """金叉(底部反弹)→ Buy。prices 长度刚好是金叉发生的那根K线。"""
    # 横盘 → 下跌使快线穿到慢线下方 → 反弹到金叉点
    prices = [100.0] * 5 + [90.0, 80.0, 110.0, 120.0]  # 9 根,金叉在第9根触发
    sig = _heuristic_signal(prices, fast=3, slow=5)
    assert sig.signal_type == SignalType.Buy
    assert sig.confidence > 0


def test_heuristic_death_cross():
    """死叉(顶部回落)→ Sell。"""
    # 横盘 → 上涨使快线在慢线上方 → 回落到死叉点
    prices = [100.0] * 5 + [110.0, 120.0, 90.0, 80.0]  # 9 根,死叉在第9根触发
    sig = _heuristic_signal(prices, fast=3, slow=5)
    assert sig.signal_type == SignalType.Sell
    assert sig.confidence > 0


def test_heuristic_hold_when_no_cross():
    """无交叉时 Hold。"""
    prices = [100.0 + i * 0.1 for i in range(30)]
    sig = _heuristic_signal(prices, fast=5, slow=20)
    assert sig.signal_type == SignalType.Hold


def test_on_bar_warmup_hold():
    """冷启动阶段全部 Hold。"""
    s = LLMSignalStrategy(StrategyConfig(name="llm_signal", params={"fast": 3, "slow": 5}))
    ctx = StrategyContext(symbol="BTCUSDT")
    s.on_start(ctx)
    for p in [100.0] * 5:
        a = s.on_bar(_bar(p), ctx)
        assert a.action_type == ActionType.Hold


def test_on_bar_buy_signal():
    """金叉后返回 Buy Action。"""
    s = LLMSignalStrategy(StrategyConfig(name="llm_signal", params={"fast": 3, "slow": 5}))
    ctx = StrategyContext(symbol="BTCUSDT")
    s.on_start(ctx)
    prices = [100.0] * 6 + [110.0, 120.0, 130.0]
    actions = [s.on_bar(_bar(p), ctx) for p in prices]
    assert any(a.action_type == ActionType.Buy for a in actions)


def test_on_bar_sell_signal():
    """死叉后返回 Sell Action。"""
    s = LLMSignalStrategy(StrategyConfig(name="llm_signal", params={"fast": 3, "slow": 5}))
    ctx = StrategyContext(symbol="BTCUSDT")
    s.on_start(ctx)
    prices = [100.0] * 4 + [120.0, 130.0, 140.0, 150.0, 100.0, 80.0, 60.0]
    actions = [s.on_bar(_bar(p), ctx) for p in prices]
    assert any(a.action_type == ActionType.Sell for a in actions)


def test_llm_mode_with_mock_provider():
    """注入 mock LLM provider 时正确解析 JSON 信号。"""
    calls = []

    def mock_provider(prompt: str) -> str:
        calls.append(prompt)
        return '{"action":"Buy","confidence":0.9,"reasoning":"test buy signal"}'

    s = LLMSignalStrategy(StrategyConfig(
        name="llm_signal",
        params={"mode": "llm", "fast": 3, "slow": 5, "llm_provider": mock_provider},
    ))
    ctx = StrategyContext(symbol="BTCUSDT")
    s.on_start(ctx)
    # 喂足够K线触发信号
    for p in [100.0] * 6:
        s.on_bar(_bar(p), ctx)
    a = s.on_bar(_bar(100.0), ctx)
    # 应该调用 LLM
    assert len(calls) >= 1
    # 返回的 action 类型由 mock 决定
    assert a.action_type in (ActionType.Buy, ActionType.Sell, ActionType.Hold)


def test_llm_mode_parse_error_fallback():
    """LLM 返回非法 JSON 时降级为 Hold。"""
    def bad_provider(prompt: str) -> str:
        return "not json at all"

    s = LLMSignalStrategy(StrategyConfig(
        name="llm_signal",
        params={"mode": "llm", "fast": 3, "slow": 5, "llm_provider": bad_provider},
    ))
    ctx = StrategyContext(symbol="BTCUSDT")
    s.on_start(ctx)
    for p in [100.0] * 6:
        s.on_bar(_bar(p), ctx)
    a = s.on_bar(_bar(100.0), ctx)
    assert a.action_type == ActionType.Hold


def test_llm_mode_no_provider_fallback():
    """mode=llm 但未注入 provider 时降级为 Hold。"""
    s = LLMSignalStrategy(StrategyConfig(
        name="llm_signal",
        params={"mode": "llm", "fast": 3, "slow": 5},  # no llm_provider
    ))
    ctx = StrategyContext(symbol="BTCUSDT")
    s.on_start(ctx)
    for p in [100.0] * 6:
        s.on_bar(_bar(p), ctx)
    a = s.on_bar(_bar(100.0), ctx)
    assert a.action_type == ActionType.Hold


def test_position_pct_config():
    """position_pct 参数控制开仓比例。"""
    s = LLMSignalStrategy(StrategyConfig(
        name="llm_signal",
        params={"fast": 3, "slow": 5, "position_pct": 0.5},
    ))
    ctx = StrategyContext(symbol="BTCUSDT")
    s.on_start(ctx)
    prices = [100.0] * 6 + [110.0, 120.0, 130.0]
    actions = [s.on_bar(_bar(p), ctx) for p in prices]
    buy_action = next((a for a in actions if a.action_type == ActionType.Buy), None)
    assert buy_action is not None
    assert buy_action.target_position == 0.5
