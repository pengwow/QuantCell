"""特征计算、问题模板、请求指纹测试。"""

from __future__ import annotations

from decision.questions import (
    ACTIONS,
    FEATURE_NAMES,
    build_questions,
    build_state,
    canonical_request,
    compute_features,
    request_fingerprint,
)


def test_features_have_frozen_names_and_round_trip_deterministic(bars_factory):
    df = bars_factory()
    f1 = compute_features(df.tail(20))
    f2 = compute_features(df.tail(20))
    assert set(f1) == set(FEATURE_NAMES)
    assert f1 == f2  # 同输入两次渲染完全一致
    # 单调上涨：ret_1 与双均线偏离为正
    assert f1["ret_1"] > 0
    assert f1["sma5_vs_sma20"] > 0


def test_volume_z_zero_when_volume_constant(bars_factory):
    df = bars_factory()
    df["volume"] = 500.0
    f = compute_features(df.tail(20))
    assert f["volume_z"] == 0.0  # std=0 不除零，返回 0


def test_build_state_shape(bars_factory):
    df = bars_factory()
    state = build_state(df.tail(20), symbol="BTCUSDT", bar_type="1h")
    assert state["symbol"] == "BTCUSDT"
    assert state["bar_type"] == "1h"
    assert len(state["window"]) == 20
    row = state["window"][0]
    assert set(row) == {"t", "o", "h", "l", "c", "v"}
    assert set(state["features"]) == set(FEATURE_NAMES)


def test_build_questions_frozen_schema():
    q = build_questions(cost_threshold=0.002)
    assert set(q) == {"next_direction", "trend_confirms", "risk_regime_bad", "signal_clarity"}
    assert q["next_direction"]["type"] == "choice"
    assert set(q["next_direction"]["criteria"]) == set(ACTIONS)
    assert q["trend_confirms"]["type"] == "noul"
    assert q["risk_regime_bad"]["type"] == "noul"
    assert q["signal_clarity"]["type"] == "score"
    assert q["signal_clarity"]["criteria"] == [
        "信号混乱，多指标互相矛盾",
        "信号一般，方向不够明确",
        "信号清晰，指标方向一致",
    ]


def test_fingerprint_stable_and_byte_sensitive(bars_factory):
    df = bars_factory()
    state = build_state(df.tail(20), symbol="BTCUSDT", bar_type="1h")
    q = build_questions(cost_threshold=0.002)
    fp1 = request_fingerprint(state, q)
    fp2 = request_fingerprint(state, q)
    assert fp1 == fp2 and len(fp1) == 64
    # state 任一字节变化 → 指纹变化
    state2 = {**state, "symbol": "ETHUSDT"}
    assert request_fingerprint(state2, q) != fp1
    # canonical_request 是 sort_keys 压缩 JSON
    assert canonical_request(state, q).startswith('{"questions":')


def test_cost_threshold_visible_in_question_text():
    q = build_questions(cost_threshold=0.003)
    text = q["next_direction"]["criteria"]["buy"]["what"]
    assert "0.30%" in text
