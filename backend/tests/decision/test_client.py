"""DecisionClient 协议的两个实现：录制回放与确定性 stub。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from decision.client import ReplayDecisionClient, ReplayMissError, StubDecisionClient
from decision.questions import build_questions, build_state, request_fingerprint
from decision.types import ChoiceAnswer, DecisionResponse, NoulAnswer, ScoreAnswer


@pytest.fixture
def state(bars_factory):
    return build_state(bars_factory().tail(20), symbol="BTCUSDT", bar_type="1h")


def test_stub_returns_valid_typed_response(state):
    resp = StubDecisionClient().decide(state, build_questions(cost_threshold=0.002))
    assert isinstance(resp, DecisionResponse)
    assert resp.model == "jev-stub"
    choice = resp.answers["next_direction"]
    assert isinstance(choice, ChoiceAnswer)
    assert choice.choice in ("buy", "sell", "hold")
    assert set(choice.probabilities) == {"buy", "sell", "hold"}
    # 三个概率各自 round(6)，求和容差按舍入误差给
    assert abs(sum(choice.probabilities.values()) - 1.0) < 1e-6
    assert 0.0 <= choice.confidence <= 1.0
    assert isinstance(resp.answers["trend_confirms"], NoulAnswer)
    assert isinstance(resp.answers["risk_regime_bad"], NoulAnswer)
    assert isinstance(resp.answers["signal_clarity"], ScoreAnswer)
    assert resp.usage.cost_usd == 0.0


def test_stub_is_deterministic(state):
    client = StubDecisionClient()
    q = build_questions(cost_threshold=0.002)
    r1 = client.decide(state, q)
    r2 = client.decide(state, q)
    assert r1.answers["next_direction"].choice == r2.answers["next_direction"].choice


def test_replay_hits_recorded_response(tmp_path: Path, state):
    q = build_questions(cost_threshold=0.002)

    recorded = {
        "model": "jev-1.13.0",
        "answers": {
            "next_direction": {
                "type": "choice",
                "choice": "sell",
                "confidence": 0.93,
                "probabilities": {"buy": 0.02, "sell": 0.93, "hold": 0.05},
            }
        },
        "usage": {"input_tokens": 10, "cost_usd": 0.00003},
    }
    line = {"fingerprint": request_fingerprint(state, q), "response": recorded}
    path = tmp_path / "rec.jsonl"
    path.write_text(json.dumps(line, ensure_ascii=False) + "\n", encoding="utf-8")

    client = ReplayDecisionClient.from_jsonl(path)
    resp = client.decide(state, q)
    assert resp.model == "jev-1.13.0"
    assert resp.answers["next_direction"].choice == "sell"


def test_replay_miss_raises_with_fingerprint(state):
    client = ReplayDecisionClient({})
    with pytest.raises(ReplayMissError) as exc:
        client.decide(state, build_questions(cost_threshold=0.002))
    assert "fingerprint" in str(exc.value)
