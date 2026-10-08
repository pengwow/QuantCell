"""REFLEX 级联决策层：Jev 直出 → 低置信兜底 → 异常兜底。

硬约束（来自统一出口契约）：
- 三条路径返回同一个 CascadeDecision 结构，禁止早退裸 dict。
- 门控只使用 Jev 原始校准 confidence，不组合综合分。
- 低置信与异常都已耗费一次 Jev 调用（异常时可能未计费），
  usage 如实透传或置 None，供成本汇总区分。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from decision.client import DecisionClient
from decision.questions import ACTIONS
from decision.types import (
    Action,
    CascadeDecision,
    ChoiceAnswer,
    DecisionResponse,
    DecisionUsage,
    NoulAnswer,
    ScoreAnswer,
)


@dataclass(frozen=True)
class CascadeConfig:
    """非对称门控：开仓阈值高于持/观望阈值。"""

    open_threshold: float = 0.80
    hold_threshold: float = 0.70


def gate_allows(action: str, confidence: float, config: CascadeConfig) -> bool:
    """置信度是否达到该动作的放行阈值（边界值放行）。"""
    threshold = config.open_threshold if action in ("buy", "sell") else config.hold_threshold
    return confidence >= threshold


class FallbackDecider(Protocol):
    """兜底决策协议；v1 是规则实现，后续可替换为 LLMFallback。"""

    def decide(self, state: dict) -> tuple[Action, dict[str, float], float]:
        """返回 (动作, buy/sell/hold 概率分布, 该动作概率即置信度)。"""


class RuleFallback:
    """确定性规则兜底：双均线偏离与近一根收益同向才开仓，否则 hold。"""

    # 各动作下的固定概率分布，probs[action] 即 confidence
    _DISTRIBUTIONS: dict[str, dict[str, float]] = {
        "buy": {"buy": 0.7, "sell": 0.1, "hold": 0.2},
        "sell": {"sell": 0.7, "buy": 0.1, "hold": 0.2},
        "hold": {"hold": 0.5, "buy": 0.25, "sell": 0.25},
    }

    def decide(self, state: dict) -> tuple[Action, dict[str, float], float]:
        f = state["features"]
        sma = float(f["sma5_vs_sma20"])
        ret = float(f["ret_1"])
        if sma > 0 and ret > 0:
            action = "buy"
        elif sma < 0 and ret < 0:
            action = "sell"
        else:
            action = "hold"
        probs = dict(self._DISTRIBUTIONS[action])
        return action, probs, probs[action]


def _extract_sub_signals(resp: DecisionResponse) -> dict[str, float]:
    """提取 3 个并行子问题信号；仅用于离线归因，禁止参与门控。"""
    sub: dict[str, float] = {}
    answers = resp.answers
    trend = answers.get("trend_confirms")
    if isinstance(trend, NoulAnswer):
        sub["trend_confirms"] = trend.noul
    risk = answers.get("risk_regime_bad")
    if isinstance(risk, NoulAnswer):
        sub["risk_regime_bad"] = risk.noul
    clarity = answers.get("signal_clarity")
    if isinstance(clarity, ScoreAnswer):
        sub["signal_clarity"] = clarity.score
    return sub


def _ensure_action_keys(probs: dict[str, float]) -> dict[str, float]:
    """补齐 buy/sell/hold 三键；保持 Jev 原始概率不归一化（校准值不可篡改）。"""
    return {name: float(probs.get(name, 0.0)) for name in ACTIONS}


class JevCascadeDecisionLayer:
    """System 1（Jev）+ 兜底的级联层，返回统一出口 CascadeDecision。"""

    def __init__(
        self,
        client: DecisionClient,
        fallback: FallbackDecider,
        config: CascadeConfig,
    ):
        self._client = client
        self._fallback = fallback
        self._config = config

    def _use_fallback(
        self,
        state: dict,
        reason: str,
        usage: DecisionUsage | None,
        sub_signals: dict[str, float],
    ) -> CascadeDecision:
        action, probs, confidence = self._fallback.decide(state)
        return CascadeDecision(
            action=action,
            source="fallback",
            confidence=confidence,
            probabilities=probs,
            fallback_reason=reason,
            jev_usage=usage,
            sub_signals=sub_signals,
        )

    def decide(self, state: dict, questions: dict) -> CascadeDecision:
        # 路径一：Jev 调用异常（含 ReplayMiss、网络、解析等），未拿到有效响应
        try:
            resp = self._client.decide(state, questions)
        except Exception as e:
            # ponytail: 兜底面故意收宽到 Exception，任何 Jev 侧失败都不能让交易循环崩掉；
            # 升级路径是按异常类型细分重试/熔断，当前预研阶段无此需求
            return self._use_fallback(state, f"jev_error: {type(e).__name__}", None, {})

        sub_signals = _extract_sub_signals(resp)
        usage = resp.usage
        choice = resp.answers.get("next_direction")

        # 路径二：响应结构无法支撑门控（主问题缺失/类型错/胜选项不在动作集）
        if not isinstance(choice, ChoiceAnswer) or choice.choice not in ACTIONS:
            return self._use_fallback(state, "jev_error: invalid_choice", usage, sub_signals)

        # 路径三：校准置信度未达非对称阈值
        if not gate_allows(choice.choice, choice.confidence, self._config):
            return self._use_fallback(
                state,
                f"low_confidence: {choice.choice}={choice.confidence}",
                usage,
                sub_signals,
            )

        # 直出：概率只补缺键不归一化，保留 Jev 原始校准分布
        return CascadeDecision(
            action=choice.choice,
            source="jev_direct",
            confidence=choice.confidence,
            probabilities=_ensure_action_keys(choice.probabilities),
            fallback_reason=None,
            jev_usage=usage,
            sub_signals=sub_signals,
        )
