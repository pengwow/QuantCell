"""decision.types 解析与统一出口类型测试。"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from decision.types import (
    CascadeDecision,
    ChoiceAnswer,
    DecisionResponse,
    DecisionUsage,
    NoulAnswer,
    ScoreAnswer,
    parse_response,
)


def test_parse_response_all_three_answer_types():
    raw = {
        "model": "jev-latest",
        "answers": {
            "next_direction": {
                "type": "choice",
                "choice": "buy",
                "confidence": 0.87,
                "probabilities": {"buy": 0.87, "sell": 0.02, "hold": 0.11},
            },
            "trend_confirms": {"type": "noul", "noul": 0.91},
            "signal_clarity": {
                "type": "score",
                "score": 2.0,
                "confidence": 0.8,
                "probabilities": {"0": 0.0, "1": 0.2, "2": 0.8},
            },
        },
        "usage": {"input_tokens": 420, "cost_usd": 0.000026},
    }
    resp = parse_response(raw)
    assert isinstance(resp, DecisionResponse)
    assert resp.model == "jev-latest"
    assert resp.usage == DecisionUsage(input_tokens=420, cost_usd=0.000026)
    choice = resp.answers["next_direction"]
    assert isinstance(choice, ChoiceAnswer)
    assert choice.choice == "buy"
    assert choice.confidence == 0.87
    noul = resp.answers["trend_confirms"]
    assert isinstance(noul, NoulAnswer)
    assert noul.noul == 0.91
    score = resp.answers["signal_clarity"]
    assert isinstance(score, ScoreAnswer)
    assert score.score == 2.0


def test_parse_response_unknown_type_raises():
    raw = {
        "model": "x",
        "answers": {"q": {"type": "essay", "text": "..."}},
        "usage": {"input_tokens": 0, "cost_usd": 0.0},
    }
    with pytest.raises(ValueError, match="question type"):
        parse_response(raw)


def test_parse_response_missing_field_raises():
    raw = {
        "model": "x",
        "answers": {"q": {"type": "choice", "choice": "buy"}},
        "usage": {"input_tokens": 0, "cost_usd": 0.0},
    }
    with pytest.raises(KeyError):
        parse_response(raw)


def test_cascade_decision_is_frozen():
    d = CascadeDecision(
        action="hold",
        source="fallback",
        confidence=0.5,
        probabilities={"buy": 0.25, "sell": 0.25, "hold": 0.5},
        fallback_reason="low_confidence",
        jev_usage=None,
        sub_signals={},
    )
    with pytest.raises(FrozenInstanceError):
        d.action = "buy"  # type: ignore[misc]
