"""离线评测数据集：CSV 加载、冻结标签口径、样本指纹。"""

from __future__ import annotations

import pytest

from decision.evaluation.dataset import (
    REQUIRED_COLUMNS,
    LabeledSample,
    build_labeled_samples,
    label_for_return,
    load_bars_csv,
)


def test_load_bars_csv_rejects_missing_columns(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("timestamp,open,high,low,close\n1,2,3,4,5\n", encoding="utf-8")
    with pytest.raises(ValueError, match="volume"):
        load_bars_csv(path)
    assert REQUIRED_COLUMNS == {"timestamp", "open", "high", "low", "close", "volume"}


def test_label_boundaries_equal_threshold_is_hold():
    assert label_for_return(0.0021, 0.002) == "buy"
    assert label_for_return(-0.0021, 0.002) == "sell"
    # 等号归 hold：扣成本后无正收益，不算可交易信号
    assert label_for_return(0.002, 0.002) == "hold"
    assert label_for_return(-0.002, 0.002) == "hold"
    assert label_for_return(0.0, 0.002) == "hold"


def test_sample_count_drops_last_horizon_bars(bars_factory):
    df = bars_factory(25)
    samples = build_labeled_samples(df, window=20, horizon=1, cost_threshold=0.002, symbol="BTCUSDT", bar_type="1h")
    # end ∈ [19, 23]：25 - 20 - 1 + 1 = 5，最后 1 根没有未来收益不产样本
    assert len(samples) == 5
    assert all(isinstance(s, LabeledSample) for s in samples)
    assert samples[0].index == 19
    assert samples[-1].index == 23


def test_fingerprint_stable_across_builds(bars_factory):
    df = bars_factory(25)
    kw = dict(window=20, horizon=1, cost_threshold=0.002, symbol="BTCUSDT", bar_type="1h")
    s1 = build_labeled_samples(df, **kw)
    s2 = build_labeled_samples(df, **kw)
    assert [a.fingerprint for a in s1] == [a.fingerprint for a in s2]
    assert len(s1[0].fingerprint) == 64


def test_state_window_length_and_label_buy_on_uptrend(bars_factory):
    df = bars_factory(25, drift=0.01)
    samples = build_labeled_samples(df, window=20, horizon=1, cost_threshold=0.0001, symbol="BTCUSDT", bar_type="1h")
    assert all(len(s.state["window"]) == 20 for s in samples)
    # 稳定上涨 + 极低阈值，所有标签应为 buy
    assert all(s.label == "buy" for s in samples)
