"""CompositeStrategy 与旧 SwarmRunner 投票路径的等价性 + 边界测试。

等价性口径: 旧路径 = SwarmOrchestrator → EventDrivenLoop 的做法:
    BaseStrategy --StrategyTrader--> SwarmRunner(voting="weighted_majority").on_bar
新路径 = CompositeStrategy.on_bar。
子策略全部是确定性假策略, 不调 LLM、不依赖随机。
"""

from __future__ import annotations

import pytest
from axon_quant.agent import SwarmRunner

from strategy import Action
from strategy.agent_traders import StrategyTrader, TraderRegistry
from strategy.base import BaseStrategy, StrategyConfig
from strategy.composite_strategy import CompositeStrategy

# 与 EventDrivenLoop.add_strategy / StrategySpec 的默认值一致
POSITION_SCALE = 0.1
# Action 的 confidence/target_position 在 Rust 侧是 f32, 与 SwarmRunner 的 f64 比较留 1e-6 容差
FLOAT_TOL = 1e-6


class FixedStrategy(BaseStrategy):
    """固定输出的假子策略。"""

    def __init__(self, name: str, action: str, confidence: float, target_position: float = 0.1):
        super().__init__(StrategyConfig(name=name))
        self._action = action
        self._confidence = confidence
        self._target_position = target_position

    def on_bar(self, bar: dict, ctx=None) -> Action:
        return Action(
            action_type=self._action,
            confidence=self._confidence,
            target_position=self._target_position,
            model_id=self.config.name,
            inference_time_us=0,
        )


class ScriptedStrategy(BaseStrategy):
    """按 close % 3 查表输出信号的无状态假策略(用于逐 bar 等价性)。"""

    def __init__(self, name: str, rules: dict[int, tuple[str, float, float]]):
        super().__init__(StrategyConfig(name=name))
        self._rules = rules

    def on_bar(self, bar: dict, ctx=None) -> Action:
        action, confidence, target_position = self._rules.get(int(bar["close"]) % 3, ("hold", 0.0, 0.0))
        return Action(
            action_type=action,
            confidence=confidence,
            target_position=target_position,
            model_id=self.config.name,
            inference_time_us=0,
        )


class BrokenStrategy(BaseStrategy):
    """每次都抛异常的子策略。"""

    def __init__(self, name: str = "broken"):
        super().__init__(StrategyConfig(name=name))

    def on_bar(self, bar: dict, ctx=None) -> Action:
        raise RuntimeError("boom")


def _bars(count: int = 24) -> list[dict]:
    return [
        {"open": 100 + i, "high": 101 + i, "low": 99 + i, "close": 100 + i, "volume": 10, "symbol": "BTCUSDT"}
        for i in range(count)
    ]


def _legacy_children() -> list[BaseStrategy]:
    """与 CompositeStrategy 测试同构的全新子策略实例(避免状态串扰)。"""
    return [
        ScriptedStrategy("s1", {0: ("buy", 0.7, 0.2), 1: ("sell", 0.6, 0.15), 2: ("hold", 0.0, 0.0)}),
        ScriptedStrategy("s2", {0: ("buy", 0.5, 0.1), 1: ("hold", 0.0, 0.0), 2: ("sell", 0.8, 0.3)}),
    ]


def _legacy_path(bar: dict) -> tuple[str, float, float]:
    """旧路径: StrategyTrader 包装 + SwarmRunner 投票 + TraderRegistry 仓位聚合。"""
    registry = TraderRegistry()
    for i, child in enumerate(_legacy_children()):
        registry.register(StrategyTrader(child, id=f"legacy_{i}", position_scale=POSITION_SCALE))

    traders = registry.get_all()
    decision = SwarmRunner(traders=traders, voting="weighted_majority").on_bar(bar)
    # EventDrivenLoop 用 collect_decisions 的原始票补齐 target_position
    aggregated_tp = registry.aggregate_target_position(registry.collect_decisions(bar))
    return decision["final_action"], decision["final_confidence"], aggregated_tp


def test_weighted_voting_matches_swarm_runner_per_bar():
    """逐 bar 对比: 投票动作、置信度、聚合 target_position 均一致。"""
    composite = CompositeStrategy(
        StrategyConfig(name="composite"),
        children=_legacy_children(),
        voting="weighted",
        position_scale=POSITION_SCALE,
    )

    for bar in _bars():
        legacy_action, legacy_confidence, legacy_tp = _legacy_path(dict(bar))
        result = composite.on_bar(dict(bar))

        assert str(result.action_type).capitalize() == legacy_action, bar
        assert result.confidence == pytest.approx(legacy_confidence, abs=FLOAT_TOL), bar

        if legacy_action != "Hold":
            assert result.target_position == pytest.approx(legacy_tp, abs=FLOAT_TOL), bar
        else:
            assert result.target_position == 0.0, bar


def test_unequal_weights_flip_winner():
    """权重不等: 低置信度的高权重票可以压过对手; 反向权重后胜者翻转。"""
    children = [
        FixedStrategy("buy_child", "buy", 0.3, 0.2),
        FixedStrategy("sell_child", "sell", 0.4, 0.2),
    ]
    bar = _bars(1)[0]

    buy_heavy = CompositeStrategy(
        StrategyConfig(name="buy_heavy"), children=children, weights=[3.0, 1.0], voting="weighted"
    )
    result = buy_heavy.on_bar(dict(bar))
    # buy=0.9, sell=0.4 → 0.9 / 1.3
    assert str(result.action_type) == "buy"
    assert result.confidence == pytest.approx(0.9 / 1.3, abs=FLOAT_TOL)

    sell_heavy = CompositeStrategy(
        StrategyConfig(name="sell_heavy"),
        children=[
            FixedStrategy("buy_child", "buy", 0.3, 0.2),
            FixedStrategy("sell_child", "sell", 0.4, 0.2),
        ],
        weights=[0.5, 2.0],
        voting="weighted",
    )
    result = sell_heavy.on_bar(dict(bar))
    # buy=0.3*0.5=0.15, sell=0.4*2=0.8 → 0.8 / 0.95
    assert str(result.action_type) == "sell"
    assert result.confidence == pytest.approx(0.8 / 0.95, abs=FLOAT_TOL)


def test_tie_breaks_toward_buy_like_swarm_runner():
    """平局: buy 与 sell 同分时按 SwarmRunner 的 >= 顺序判 buy。"""
    composite = CompositeStrategy(
        StrategyConfig(name="tie"),
        children=[FixedStrategy("b", "buy", 0.5), FixedStrategy("s", "sell", 0.5)],
        voting="weighted",
    )
    result = composite.on_bar(_bars(1)[0])
    assert str(result.action_type) == "buy"
    # normalized = 0.5 / 1.0, 恰好等于阈值, 不改判 Hold
    assert result.confidence == pytest.approx(0.5, abs=FLOAT_TOL)


def test_hold_vote_participates_with_min_score():
    """Hold 票按 max(confidence, 0.1) 参与比较; 0.0 置信度经 StrategyTrader 兜底成 0.5。"""
    bar = _bars(1)[0]

    # buy 0.8 vs hold 0.5(0.0 被兜底) → buy 胜
    buy_wins = CompositeStrategy(
        StrategyConfig(name="hold_minor"),
        children=[FixedStrategy("b", "buy", 0.8), FixedStrategy("h", "hold", 0.0, 0.0)],
        voting="weighted",
    )
    result = buy_wins.on_bar(dict(bar))
    assert str(result.action_type) == "buy"
    assert result.confidence == pytest.approx(0.8 / 1.3, abs=FLOAT_TOL)

    # buy 0.4 vs hold 0.5 → hold 胜; 归一化得分 >= 0.5, 保持 Hold
    hold_wins = CompositeStrategy(
        StrategyConfig(name="hold_major"),
        children=[FixedStrategy("b", "buy", 0.4), FixedStrategy("h", "hold", 0.0, 0.0)],
        voting="weighted",
    )
    result = hold_wins.on_bar(dict(bar))
    assert str(result.action_type) == "hold"
    assert result.confidence == pytest.approx(0.5 / 0.9, abs=FLOAT_TOL)
    assert result.target_position == 0.0


def test_child_exception_is_skipped_not_fatal():
    """子策略抛异常: 记 warning 并跳票, 剩余票照常决策; 全崩则 Hold。"""
    bar = _bars(1)[0]

    composite = CompositeStrategy(
        StrategyConfig(name="partial"),
        children=[BrokenStrategy(), FixedStrategy("b", "buy", 0.6)],
        voting="weighted",
    )
    result = composite.on_bar(dict(bar))
    # 只剩一张 buy 0.6 → normalized = 0.6 / 0.6 = 1.0
    assert str(result.action_type) == "buy"
    assert result.confidence == pytest.approx(1.0, abs=FLOAT_TOL)

    all_broken = CompositeStrategy(
        StrategyConfig(name="all_broken"), children=[BrokenStrategy("a"), BrokenStrategy("b")], voting="weighted"
    )
    result = all_broken.on_bar(dict(bar))
    assert str(result.action_type) == "hold"
    assert result.confidence == 0.0
    assert result.target_position == 0.0


def test_majority_mode_counts_weights():
    """majority 模式按权重计票, 不看 confidence。"""
    composite = CompositeStrategy(
        StrategyConfig(name="majority"),
        children=[FixedStrategy("b", "buy", 0.1), FixedStrategy("s", "sell", 0.9)],
        weights=[2.0, 1.0],
        voting="majority",
    )
    result = composite.on_bar(_bars(1)[0])
    assert str(result.action_type) == "buy"
    assert result.confidence == pytest.approx(2.0 / 3.0, abs=FLOAT_TOL)


def test_invalid_config_raises():
    """构造期校验: 空子策略 / 权重错位 / 非法投票模式。"""
    with pytest.raises(ValueError):
        CompositeStrategy(StrategyConfig(name="x"), children=[])
    with pytest.raises(ValueError):
        CompositeStrategy(
            StrategyConfig(name="x"), children=[FixedStrategy("b", "buy", 0.5)], weights=[1.0, 2.0]
        )
    with pytest.raises(ValueError):
        CompositeStrategy(
            StrategyConfig(name="x"), children=[FixedStrategy("b", "buy", 0.5)], voting="unanimous"
        )
