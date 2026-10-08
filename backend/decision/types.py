"""Jev 决策协议类型。

字段名严格对齐 Jev 官方 API（type/instructions/criteria；
答案 noul/choice/score/confidence/probabilities），录制 JSON 与真实
响应零转换。统一出口 CascadeDecision 是 cascade 所有分支的唯一返回类型，
禁止任何分支返回裸 dict 或缺字段对象。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# 三种交易动作，概率 dict 的键恒为这三个（顺序固定）
ACTIONS: tuple[str, ...] = ("buy", "sell", "hold")
Action = Literal["buy", "sell", "hold"]


@dataclass(frozen=True)
class DecisionUsage:
    """单次决策的真实计费信息（成本测算只允许引用这两个字段）。"""

    input_tokens: int
    cost_usd: float


@dataclass(frozen=True)
class NoulAnswer:
    """是/否命题答案：noul 即命题成立的校准概率 0–1。"""

    noul: float


@dataclass(frozen=True)
class ChoiceAnswer:
    """有界单选答案：胜选项 + 校准置信 + 全选项概率分布。"""

    choice: str
    confidence: float
    probabilities: dict[str, float]


@dataclass(frozen=True)
class ScoreAnswer:
    """有序量表答案：概率加权得分 + 各等级概率。"""

    score: float
    confidence: float
    probabilities: dict[str, float]


Answer = NoulAnswer | ChoiceAnswer | ScoreAnswer


@dataclass(frozen=True)
class DecisionResponse:
    """Jev /v1/systemone 单次响应的解析结果。"""

    model: str
    answers: dict[str, Answer]
    usage: DecisionUsage


@dataclass(frozen=True)
class CascadeDecision:
    """cascade 统一出口（直出/低置信/异常三分支同构）。

    - source=fallback 时 fallback_reason 必填。
    - probabilities 的 buy/sell/hold 三键恒在。
    - sub_signals 仅供离线归因，禁止参与门控。
    """

    action: Action
    source: Literal["jev_direct", "fallback"]
    confidence: float
    probabilities: dict[str, float]
    fallback_reason: str | None
    jev_usage: DecisionUsage | None
    sub_signals: dict[str, float]


def _parse_answer(raw: dict) -> Answer:
    kind = raw.get("type")
    if kind == "noul":
        return NoulAnswer(noul=float(raw["noul"]))
    if kind == "choice":
        return ChoiceAnswer(
            choice=str(raw["choice"]),
            confidence=float(raw["confidence"]),
            probabilities={k: float(v) for k, v in raw["probabilities"].items()},
        )
    if kind == "score":
        return ScoreAnswer(
            score=float(raw["score"]),
            confidence=float(raw["confidence"]),
            probabilities={k: float(v) for k, v in raw["probabilities"].items()},
        )
    raise ValueError(f"unknown question type: {kind!r}")


def parse_response(raw: dict) -> DecisionResponse:
    """把 Jev 原始 JSON（或 stub 构造的同构 dict）解析为 DecisionResponse。

    缺字段直接抛 KeyError/ValueError，由 cascade 统一走 jev_error 分支，
    不在此做静默兜底。
    """
    return DecisionResponse(
        model=str(raw["model"]),
        answers={k: _parse_answer(v) for k, v in raw["answers"].items()},
        usage=DecisionUsage(
            input_tokens=int(raw["usage"]["input_tokens"]),
            cost_usd=float(raw["usage"]["cost_usd"]),
        ),
    )
