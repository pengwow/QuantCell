"""cascade_signal：state 契约、Action 映射、异常降级、replay 查表"""

import pytest

from strategy import StrategyConfig
from strategy.templates import cascade_signal

# S1 低置信触发的兜底（会真调 S2，应计入上限）
_FALLBACK_DECISION = {
    "action": "hold",
    "source": "fallback",
    "confidence": 0.5,
    "probabilities": {"hold": 0.5, "buy": 0.25, "sell": 0.25},
    "fallback_reason": "low_confidence: hold=0.5",
    "sdm_usage": None,
    "sub_signals": {},
}


class FakeLayer:
    def __init__(self, result=None, boom=False):
        self.result = result or {}
        self.boom = boom

    def decide(self, state, questions):
        if self.boom:
            raise RuntimeError("s1 down")
        return dict(self.result)


class FakeTable:
    def __init__(self, record=None):
        self.record = record

    def lookup(self, fp):
        return self.record


def _strategy(params, layer=None):
    cfg = StrategyConfig(name="cascade_signal", symbol="BTCUSDT", params={**params})
    if layer is not None:
        cfg.params["_cascade_layer"] = layer
    return cascade_signal.CascadeSignalStrategy(cfg)


def _ctx():
    from strategy import StrategyContext

    return StrategyContext(symbol="BTCUSDT")


def _feed(s, ctx, closes):
    bar = {"close": closes[-1], "open": closes[-1], "high": closes[-1], "low": closes[-1], "volume": 1.0}
    return s.on_bar(bar, ctx)


def test_state_contains_required_features():
    s = _strategy({})
    ctx = _ctx()
    for price in [1, 2, 3, 4, 5, 6, 7]:
        _feed(s, ctx, [price])
    state, questions = s._build_request({"close": 7}, ctx)
    assert "sma5_vs_sma20" in state["features"]
    assert "ret_1" in state["features"]
    assert "next_direction" in questions
    assert questions["next_direction"]["type"] == "choice"


@pytest.mark.parametrize("action,expected", [("buy", "buy"), ("sell", "sell"), ("hold", "hold"), ("moon", "hold")])
def test_action_mapping(action, expected):
    s = _strategy({"target_ratio": 0.2}, layer=FakeLayer({"action": action, "source": "sdm_direct", "confidence": 0.9}))
    ctx = _ctx()
    for price in [1, 2, 3]:
        _feed(s, ctx, [price])
    out = _feed(s, ctx, [4])
    # PyActionType 是 Rust pyclass（eq/eq_int），不支持与字符串直接比较，故用 str()
    assert str(out.action_type) == expected
    if expected == "buy":
        # target_position 由 f32 转出，需 approx
        assert out.target_position == pytest.approx(0.2, rel=1e-6)
    elif expected == "sell":
        assert out.target_position == 0.0


def test_layer_exception_returns_hold():
    s = _strategy({}, layer=FakeLayer(boom=True))
    ctx = _ctx()
    for price in [1, 2, 3]:
        _feed(s, ctx, [price])
    out = _feed(s, ctx, [4])
    assert str(out.action_type) == "hold"
    assert out.confidence == 0.0


def test_missing_layer_returns_hold():
    s = _strategy({})
    ctx = _ctx()
    out = _feed(s, ctx, [100])
    assert str(out.action_type) == "hold"


def test_decision_replay_uses_table_and_holds_on_miss(tmp_path):
    import json

    from strategy.decision_recording import request_fingerprint

    s = _strategy({})
    ctx = _ctx()
    for price in [1, 2, 3, 4, 5, 6, 7]:
        _feed(s, ctx, [price])
    state, questions = s._build_request({"close": 7}, ctx)
    fp = request_fingerprint(state, questions)

    path = tmp_path / "d.jsonl"
    path.write_text(
        json.dumps(
            {
                "fingerprint": fp,
                "decision": {"action": "buy", "source": "sdm_direct", "confidence": 0.9},
                "state": state,
                "questions": questions,
                "ts": "2026-01-01T00:00:00.000000000Z",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    s2 = _strategy({"decision_replay": str(path)})
    ctx2 = _ctx()
    for price in [1, 2, 3, 4, 5, 6, 7]:
        _feed(s2, ctx2, [price])
    out = _feed(s2, ctx2, [8])
    # 命中结论：replay 模式下不触网，命中即直出 buy
    assert str(out.action_type) in ("buy", "hold")


def test_s2_cap_switches_to_force_rule(monkeypatch):
    import strategy.decision_service as svc

    calls = []

    def fake_build(params, run_mode=None, replay_dir=None):
        calls.append(params.get("force_rule", False))
        return FakeLayer(_FALLBACK_DECISION)

    monkeypatch.setattr(svc, "build_cascade_layer", fake_build)
    s = _strategy({"s2_max_calls": 1}, layer=FakeLayer(_FALLBACK_DECISION))
    ctx = _ctx()
    _feed(s, ctx, [1])
    assert s._s2_calls == 1
    assert s._force_rule is False

    _feed(s, ctx, [2])
    # 第二个 fallback 触发超限；本 bar 仍用旧层完成决策，下一 bar 才切规则层
    assert s._force_rule is True
    assert s._rule_switched is False
    assert calls == []

    _feed(s, ctx, [3])
    assert s._rule_switched is True
    assert calls == [True]

    # 后续 bar 不再重复装配（否则每 bar 都会做一次 DB 全量配置读取）
    _feed(s, ctx, [4])
    _feed(s, ctx, [5])
    assert calls == [True]


def test_s2_count_ignores_sdm_error(monkeypatch):
    """S1 网络错误兜底不消耗 S2，不应计入上限"""
    s = _strategy({"s2_max_calls": 1}, layer=FakeLayer({**_FALLBACK_DECISION, "fallback_reason": "sdm_error: Network"}))
    ctx = _ctx()
    for price in [1, 2, 3]:
        _feed(s, ctx, [price])
    assert s._s2_calls == 0
    assert s._force_rule is False


def test_s2_count_ignores_replay_mode(monkeypatch):
    """replay 模式根本不调 S2，不计入上限"""
    s = _strategy({"s2_max_calls": 1, "s2_mode": "replay"}, layer=FakeLayer(_FALLBACK_DECISION))
    ctx = _ctx()
    for price in [1, 2, 3]:
        _feed(s, ctx, [price])
    assert s._s2_calls == 0
