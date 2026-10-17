"""v2 问题模板与特征集的单元测试。

覆盖：
- FEATURE_NAMES_V2 冻结表（与 v1 零漂移）
- compute_features_v2() 输出 8 个特征
- build_questions_v2() 返回 8 个问题、类型正确
- build_full_v2() 端到端
- v2 stub 输出 8 个答案
- v1 问题模板下 stub 不输出 v2 答案（向后兼容）
"""

from __future__ import annotations

import pandas as pd
import pytest

from decision.cascade import CascadeConfig, _extract_sub_signals, gate_allows
from decision.client import StubDecisionClient
from decision.quant_questions import (
    FEATURE_NAMES_V2,
    build_full_v2,
    build_questions_v2,
    build_state_v2,
    compute_features_v2,
    request_fingerprint,
)
from decision.questions import build_questions as build_questions_v1
from decision.questions import build_state as build_state_v1
from decision.types import ChoiceAnswer, DecisionResponse, NoulAnswer, ScoreAnswer

# ── Fixture: 构造 >= 20 根 bar 的 window ── #


@pytest.fixture
def window() -> pd.DataFrame:
    import numpy as np

    np.random.seed(123)
    n = 25
    close = 100 + np.cumsum(np.random.randn(n) * 0.3)
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-06-01", periods=n, freq="5min").astype("int64") // 10**6,
            "open": close + np.random.randn(n) * 0.1,
            "high": close + abs(np.random.randn(n) * 0.2),
            "low": close - abs(np.random.randn(n) * 0.2),
            "close": close,
            "volume": np.random.randint(1000, 5000, n).astype(float),
        }
    )


# ── FEATURE_NAMES_V2 冻结表 ── #


def test_feature_names_v2_count_and_split():
    assert len(FEATURE_NAMES_V2) == 8
    # v1 前 5 个（与 v1 compute_features 零漂移）
    assert FEATURE_NAMES_V2[0] == "ret_1"
    assert FEATURE_NAMES_V2[1] == "ret_5"
    assert FEATURE_NAMES_V2[2] == "vol_20"
    assert FEATURE_NAMES_V2[3] == "sma5_vs_sma20"
    assert FEATURE_NAMES_V2[4] == "volume_z"
    # v2 新增 3 个
    assert FEATURE_NAMES_V2[5] == "close_vs_sma20"
    assert FEATURE_NAMES_V2[6] == "rsi_14"
    assert FEATURE_NAMES_V2[7] == "volume_ratio"


def test_v1_feature_values_identical_to_v1_implementation(window):
    """v2 的前 5 个特征必须与 v1 compute_features 输出零漂移（同一算法、同一数据）。"""
    v1_state = build_state_v1(window, symbol="X", bar_type="1m")
    v1_feats = v1_state["features"]
    v2_state = build_state_v2(window, symbol="X", bar_type="1m")
    v2_feats = v2_state["features"]
    for name in ("ret_1", "ret_5", "vol_20", "sma5_vs_sma20", "volume_z"):
        assert v1_feats[name] == v2_feats[name], f"v1/v2 mismatch for {name}"


# ── compute_features_v2 ── #


def test_compute_features_v2_returns_all_8(window):
    feats = compute_features_v2(window)
    assert set(feats.keys()) == set(FEATURE_NAMES_V2)
    for val in feats.values():
        assert isinstance(val, float)


def test_compute_features_v2_rsi_in_valid_range(window):
    feats = compute_features_v2(window)
    assert 0.0 <= feats["rsi_14"] <= 100.0


# ── build_questions_v2 ── #


def test_build_questions_v2_has_8_keys():
    q = build_questions_v2(cost_threshold=0.002)
    assert len(q) == 8
    for k in [
        "next_direction",
        "trend_confirms",
        "risk_regime_bad",
        "signal_clarity",
        "position_size",
        "volatility_regime",
        "drawdown_risk",
        "execution_urgency",
    ]:
        assert k in q


def test_build_questions_v2_types():
    q = build_questions_v2(cost_threshold=0.002)
    assert q["next_direction"]["type"] == "choice"
    assert q["trend_confirms"]["type"] == "noul"
    assert q["risk_regime_bad"]["type"] == "noul"
    assert q["signal_clarity"]["type"] == "score"
    assert q["position_size"]["type"] == "choice"
    assert q["volatility_regime"]["type"] == "score"
    assert q["drawdown_risk"]["type"] == "noul"
    assert q["execution_urgency"]["type"] == "choice"


def test_cost_threshold_appears_in_criteria_text():
    q = build_questions_v2(cost_threshold=0.0025)
    buy_what = q["next_direction"]["criteria"]["buy"]["what"]
    assert "0.25%" in buy_what


# ── Stub v2 输出 ── #


def test_stub_outputs_v2_answers_when_v2_questions_present(window):
    state, questions = build_full_v2(window, symbol="BTCUSDT", bar_type="1m", cost_threshold=0.002)
    resp = StubDecisionClient().decide(state, questions)
    # v1 全部 4 个
    for key in ("next_direction", "trend_confirms", "risk_regime_bad", "signal_clarity"):
        assert key in resp.answers, f"missing v1 key: {key}"
    # v2 全部 4 个
    for key in ("position_size", "volatility_regime", "drawdown_risk", "execution_urgency"):
        assert key in resp.answers, f"missing v2 key: {key}"


def test_stub_does_NOT_output_v2_answers_when_v1_questions_only(window):
    """只给 v1 问题时，stub 不得输出 v2 新增的 4 个答案（向后兼容）。"""
    state_v1 = build_state_v1(window, symbol="X", bar_type="1m")
    questions_v1 = build_questions_v1(cost_threshold=0.002)
    resp = StubDecisionClient().decide(state_v1, questions_v1)
    for key in ("position_size", "volatility_regime", "drawdown_risk", "execution_urgency"):
        assert key not in resp.answers, f"stub should NOT output v2 key: {key}"


# ── sub_signals 提取 ── #


def test_sub_signals_extracts_v2_numeric(window):
    """v2 响应的 volatility_regime (Score) 和 drawdown_risk (Noul) 必须进入 sub_signals。"""
    state, questions = build_full_v2(window, symbol="X", bar_type="1m", cost_threshold=0.002)
    resp = StubDecisionClient().decide(state, questions)
    sub = _extract_sub_signals(resp)
    # v1 3 个
    assert "trend_confirms" in sub
    assert "risk_regime_bad" in sub
    assert "signal_clarity" in sub
    # v2 新增可数值化的 2 个
    assert "volatility_regime" in sub
    assert "drawdown_risk" in sub
    # position_size 和 execution_urgency 是 Choice，不提取
    assert "position_size" not in sub
    assert "execution_urgency" not in sub
