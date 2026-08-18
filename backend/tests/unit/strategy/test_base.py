"""BaseStrategy 抽象测试。"""

import pytest

from axon_bridge import Action
from strategy.base import BaseStrategy, StrategyConfig, StrategyContext


class StubStrategy(BaseStrategy):
    def on_bar(self, bar, ctx):
        return Action(
            action_type="hold",
            confidence=0.0,
            target_position=0.0,
            model_id="stub",
            inference_time_us=0,
        )


def test_base_strategy_is_abstract():
    """BaseStrategy 是抽象类，不能直接实例化。"""
    with pytest.raises(TypeError):
        BaseStrategy(StrategyConfig(name="x"))


def test_subclass_must_implement_on_bar():
    """子类必须实现 on_bar。"""

    class Missing(BaseStrategy):
        pass

    with pytest.raises(TypeError):
        Missing(StrategyConfig(name="x"))


def test_strategy_config_defaults():
    """StrategyConfig 默认值。"""
    cfg = StrategyConfig(name="dual_ma")
    assert cfg.interval == 1.0
    assert cfg.position_limit == 0.1
    assert cfg.params == {}


def test_strategy_context_defaults():
    """StrategyContext 默认空容器。"""
    ctx = StrategyContext(symbol="BTCUSDT")
    assert ctx.closes == []
    assert ctx.positions == {}
    assert ctx.orders == []


def test_subclass_can_be_instantiated():
    """StubStrategy 可正常实例化 + on_bar 返回 Action。"""
    s = StubStrategy(StrategyConfig(name="stub"))
    ctx = StrategyContext(symbol="BTCUSDT")
    action = s.on_bar({"close": 100}, ctx)
    assert str(action.action_type) == "hold"
    assert action.model_id == "stub"
