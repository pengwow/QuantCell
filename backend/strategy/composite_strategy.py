"""CompositeStrategy — 把多策略投票收编为一个可注册策略(M5)。

背景: 旧路径是 EventDrivenLoop 把每个规则策略包装成 StrategyTrader, 再交给
axon_quant.agent.SwarmRunner 做 weighted_majority 投票。M5 把这套投票收编成
一个 BaseStrategy, 让统一内核 add_strategy 一次即可注册多策略组合,
且投票结果与旧路径保持等价。

逐条对齐来源:
1. 投票归一化 —— strategy/agent_traders.py::StrategyTrader.decide:
   - action_type 转小写, 只认 buy/sell/hold, 其余按 hold
   - confidence 走 `getattr(action, "confidence", 0.5) or 0.5` (0.0/None 兜底成 0.5,
     这是现有路径的真实口径, 不是笔误)
   - target_position 为 0 且非 hold 时回退 `confidence * position_scale`
2. 加权聚合 —— axon_quant/agent/swarm.py::SwarmRunner._on_bar_python, 与 Rust
   `WeightedMajorityVote::aggregate` 同公式:
   - Buy/Sell 逐票累加 confidence; Hold 每票按 max(confidence, 0.1) 计
   - 平局顺序 Buy >= Sell >= Hold (先比 buy, 再比 sell)
   - normalized = 胜出得分 / 三类总分; normalized < 0.5 时改判 Hold,
     但 confidence 仍保留 normalized (SwarmRunner 原样返回 score)
3. 仓位聚合 —— strategy/agent_traders.py::TraderRegistry.aggregate_target_position:
   - 所有票(含 Hold / 反向票)按 confidence 加权平均, 置信度权重和为 0 时返回 0
   - 复合策略在分子分母各乘一次子策略权重, 等权时与原公式完全一致
4. 子策略异常 —— 记 warning 并跳过该票, 不让整个复合策略崩。
   (llm_signal 有 except → Hold 的先例; 这里按 M5 要求跳票, 避免异常票污染 Hold 得分)

不在本类做风控: SwarmRunner 的 risk_verdict 交给内核 RiskEngine, 复合策略只负责投票。

ponytail: majority 是计数模式(按权重计票, 平局顺序同上); SwarmRunner 只有
         weighted_majority/unanimous, 因此"与 SwarmRunner 等价"的承诺只覆盖
         voting="weighted", majority 是新增模式。
"""

from __future__ import annotations

from dataclasses import dataclass

from axon_bridge import Action
from utils.logger import LogType, get_logger

from .base import BaseStrategy, StrategyConfig, StrategyContext

logger = get_logger(__name__, LogType.APPLICATION)

_ACTIONS = ("buy", "sell", "hold")
# SwarmRunner 的 Hold 最低分, 见 axon_quant/agent/swarm.py::_on_bar_python
_HOLD_MIN_SCORE = 0.1
# SwarmRunner 的胜出阈值, 见 SwarmRunner._on_bar_python / WeightedMajorityVote::default
_VOTE_THRESHOLD = 0.5

_VOTING_MODES = ("weighted", "majority")


@dataclass(slots=True)
class _Vote:
    """单张票: 已按 StrategyTrader 口径归一化后的子策略输出。"""

    action: str
    confidence: float
    target_position: float
    weight: float


class CompositeStrategy(BaseStrategy):
    """多个 BaseStrategy 的投票复合策略。

    用法:
        composite = CompositeStrategy(
            StrategyConfig(name="swarm_composite"),
            children=[DualMA(cfg1), RsiReversal(cfg2)],
            weights=[2.0, 1.0],
            voting="weighted",
        )
        action = composite.on_bar(bar, ctx)
    """

    def __init__(
        self,
        config: StrategyConfig,
        children: list[BaseStrategy],
        weights: list[float] | None = None,
        voting: str = "weighted",
        position_scale: float = 0.1,
    ):
        """
        Args:
            config: 复合策略自身的配置(name 会写进 model_id)
            children: 子策略列表, 必须是 BaseStrategy
            weights: 与 children 等长的投票权重, 缺省全 1.0
            voting: "weighted"(confidence 加权, 等价 SwarmRunner) / "majority"(按权重计票)
            position_scale: 子策略没给 target_position 时的回退比例,
                对齐 EventDrivenLoop.add_strategy / StrategySpec 的默认 0.1
        """
        super().__init__(config)
        if not children:
            raise ValueError("CompositeStrategy 至少需要一个子策略")
        if voting not in _VOTING_MODES:
            raise ValueError(f"不支持的投票模式: {voting!r}, 可选 {_VOTING_MODES}")

        resolved_weights = [1.0] * len(children) if weights is None else [float(w) for w in weights]
        if len(resolved_weights) != len(children):
            raise ValueError(f"weights 数量({len(resolved_weights)})与子策略数量({len(children)})不一致")
        if any(w < 0 for w in resolved_weights):
            raise ValueError("投票权重不能为负")
        if sum(resolved_weights) <= 0:
            raise ValueError("投票权重之和必须大于 0")

        self._children = list(children)
        self._weights = resolved_weights
        self._voting = voting
        self._position_scale = float(position_scale)

    # ─── 生命周期 ───

    def on_start(self, ctx: StrategyContext | None = None) -> None:
        super().on_start(ctx)
        for child in self._children:
            child.on_start(ctx)

    def on_stop(self, ctx: StrategyContext | None = None) -> None:
        for child in self._children:
            child.on_stop(ctx)

    # ─── 核心 ───

    def on_bar(self, bar: dict, ctx: StrategyContext | None = None) -> Action:
        votes = self._collect_votes(bar, ctx)
        if self._voting == "majority":
            action, confidence = self._majority_result(votes)
        else:
            action, confidence = self._weighted_result(votes)

        # Hold 不携带仓位意图, target_position 清零 (与 EventDrivenLoop 的 hold 语义一致)
        target_position = 0.0 if action == "hold" else self._aggregate_target_position(votes)

        return Action(
            action_type=action,
            confidence=confidence,
            target_position=target_position,
            model_id=self.config.name,
            inference_time_us=0,
        )

    def _collect_votes(self, bar: dict, ctx: StrategyContext | None) -> list[_Vote]:
        """依次调用子策略并归一化为投票; 异常票记 warning 后跳过。"""
        votes: list[_Vote] = []
        for child, weight in zip(self._children, self._weights, strict=True):
            try:
                try:
                    action = child.on_bar(bar, ctx)
                except TypeError:
                    # 兼容只接受 bar 的旧策略, 与 StrategyTrader.decide 的降级调用一致
                    action = child.on_bar(bar)
            except Exception as e:
                logger.warning(f"CompositeStrategy 子策略 {child.__class__.__name__} 决策失败, 跳过该票: {e}")
                continue

            action_type = str(getattr(action, "action_type", "")).lower()
            if action_type not in _ACTIONS:
                action_type = "hold"
            confidence = float(getattr(action, "confidence", 0.5) or 0.5)
            target_position = float(getattr(action, "target_position", 0.0) or 0.0)
            if target_position == 0 and action_type != "hold":
                target_position = confidence * self._position_scale

            votes.append(
                _Vote(
                    action=action_type,
                    confidence=confidence,
                    target_position=target_position,
                    weight=weight,
                )
            )
        return votes

    def _weighted_result(self, votes: list[_Vote]) -> tuple[str, float]:
        """confidence 加权投票, 公式逐项对齐 SwarmRunner._on_bar_python。"""
        if not votes:
            return "hold", 0.0

        scores = dict.fromkeys(_ACTIONS, 0.0)
        for vote in votes:
            if vote.action == "hold":
                # Hold 也参与比较, 但每票至少记 0.1 分 (SwarmRunner 的 max(conf, 0.1))
                scores["hold"] += vote.weight * max(vote.confidence, _HOLD_MIN_SCORE)
            else:
                scores[vote.action] += vote.weight * vote.confidence

        total = sum(scores.values())
        if total <= 0:
            return "hold", 0.0

        action, raw_score = _pick_winner(scores)
        confidence = raw_score / total
        # 低于阈值一律 Hold, 但 confidence 保留归一化得分 (SwarmRunner 不改写 score)
        if confidence < _VOTE_THRESHOLD:
            return "hold", confidence
        return action, confidence

    def _majority_result(self, votes: list[_Vote]) -> tuple[str, float]:
        """按权重计票的多数投票(新增模式, 无 SwarmRunner 对应实现)。

        每张票计 weight 票, 平局顺序与 weighted 模式一致; confidence = 胜出权重占比。
        """
        if not votes:
            return "hold", 0.0

        scores = dict.fromkeys(_ACTIONS, 0.0)
        for vote in votes:
            scores[vote.action] += vote.weight

        total = sum(scores.values())
        if total <= 0:
            return "hold", 0.0

        action, raw_score = _pick_winner(scores)
        return action, raw_score / total

    @staticmethod
    def _aggregate_target_position(votes: list[_Vote]) -> float:
        """confidence 加权平均, 对齐 TraderRegistry.aggregate_target_position。"""
        weighted = 0.0
        weight_sum = 0.0
        for vote in votes:
            w = vote.weight * vote.confidence
            weighted += w * vote.target_position
            weight_sum += w
        if weight_sum <= 0:
            return 0.0
        return round(weighted / weight_sum, 6)


def _pick_winner(scores: dict[str, float]) -> tuple[str, float]:
    """胜出动作; 平局按 buy > sell > hold 顺序(对齐 SwarmRunner 的 >= 比较)。"""
    if scores["buy"] >= scores["sell"] and scores["buy"] >= scores["hold"]:
        return "buy", scores["buy"]
    if scores["sell"] >= scores["buy"] and scores["sell"] >= scores["hold"]:
        return "sell", scores["sell"]
    return "hold", scores["hold"]
