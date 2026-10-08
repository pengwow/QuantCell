"""cascade 三条出口路径：直出 / 低置信兜底 / 异常兜底。"""

from __future__ import annotations

import pytest

from decision.cascade import (
    CascadeConfig,
    JevCascadeDecisionLayer,
    RuleFallback,
    gate_allows,
)
from decision.client import DecisionError
from decision.questions import build_questions
from decision.types import DecisionUsage, parse_response

Q = build_questions(cost_threshold=0.002)
STATE = {"features": {"sma5_vs_sma20": 0.01, "ret_1": 0.002, "volume_z": 0.3}}


def _resp(choice: str, conf: float, *, cost: float = 0.00003):
    probs = {"buy": 0.0, "sell": 0.0, "hold": 0.0}
    probs[choice] = conf
    return parse_response(
        {
            "model": "jev-latest",
            "answers": {
                "next_direction": {
                    "type": "choice",
                    "choice": choice,
                    "confidence": conf,
                    "probabilities": probs,
                },
                "trend_confirms": {"type": "noul", "noul": 0.9},
            },
            "usage": {"input_tokens": 100, "cost_usd": cost},
        }
    )


class _ScriptedClient:
    def __init__(self, resp=None, exc: Exception | None = None):
        self._resp = resp
        self._exc = exc

    def decide(self, state, questions):
        if self._exc is not None:
            raise self._exc
        return self._resp


def test_gate_allows_asymmetric_thresholds():
    cfg = CascadeConfig()
    assert gate_allows("buy", 0.80, cfg)
    assert not gate_allows("buy", 0.79, cfg)
    assert gate_allows("hold", 0.70, cfg)
    assert not gate_allows("hold", 0.69, cfg)


def test_high_confidence_direct_path():
    layer = JevCascadeDecisionLayer(_ScriptedClient(_resp("buy", 0.9)), RuleFallback(), CascadeConfig())
    d = layer.decide(STATE, Q)
    assert d.source == "jev_direct"
    assert d.action == "buy"
    assert d.fallback_reason is None
    assert d.jev_usage == DecisionUsage(100, 0.00003)
    assert set(d.probabilities) == {"buy", "sell", "hold"}
    assert d.sub_signals["trend_confirms"] == 0.9


def test_low_confidence_fallback_keeps_jev_usage():
    layer = JevCascadeDecisionLayer(_ScriptedClient(_resp("buy", 0.6, cost=0.00003)), RuleFallback(), CascadeConfig())
    d = layer.decide(STATE, Q)
    assert d.source == "fallback"
    assert d.fallback_reason is not None and d.fallback_reason.startswith("low_confidence")
    # 低置信也已产生一次 Jev 计费，usage 必须保留用于成本核算
    assert d.jev_usage == DecisionUsage(100, 0.00003)
    assert set(d.probabilities) == {"buy", "sell", "hold"}


def test_client_error_fallback_has_no_usage():
    layer = JevCascadeDecisionLayer(_ScriptedClient(exc=DecisionError("boom")), RuleFallback(), CascadeConfig())
    d = layer.decide(STATE, Q)
    assert d.source == "fallback"
    assert d.fallback_reason is not None and "jev_error" in d.fallback_reason
    assert d.jev_usage is None


def test_invalid_choice_value_falls_back():
    bad = parse_response(
        {
            "model": "x",
            "answers": {
                "next_direction": {
                    "type": "choice",
                    "choice": "wait",
                    "confidence": 0.99,
                    "probabilities": {"wait": 1.0},
                }
            },
            "usage": {"input_tokens": 0, "cost_usd": 0.0},
        }
    )
    layer = JevCascadeDecisionLayer(_ScriptedClient(bad), RuleFallback(), CascadeConfig())
    d = layer.decide(STATE, Q)
    assert d.source == "fallback"
    assert "jev_error" in d.fallback_reason


def test_rule_fallback_directions():
    fb = RuleFallback()
    up = {"features": {"sma5_vs_sma20": 0.01, "ret_1": 0.01}}
    down = {"features": {"sma5_vs_sma20": -0.01, "ret_1": -0.01}}
    mixed = {"features": {"sma5_vs_sma20": 0.01, "ret_1": -0.01}}
    assert fb.decide(up)[0] == "buy"
    assert fb.decide(down)[0] == "sell"
    assert fb.decide(mixed)[0] == "hold"
    for state in (up, down, mixed):
        action, probs, conf = fb.decide(state)
        assert set(probs) == {"buy", "sell", "hold"}
        assert abs(sum(probs.values()) - 1.0) < 1e-9
        assert probs[action] == conf
