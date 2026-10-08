"""离线评测编排：缓存 Jev 响应 → 门控 → 指标 → 60/40 切分 → 阈值推荐。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import pytest

from decision.cascade import CascadeConfig, JevCascadeDecisionLayer, RuleFallback
from decision.client import StubDecisionClient
from decision.evaluation.evaluator import EvalConfig, run_evaluation
from decision.types import DecisionResponse


def _cfg(bars, **kw):
    defaults = dict(
        bars=bars,
        client=StubDecisionClient(),
        fallback=RuleFallback(),
        symbol="BTCUSDT",
        bar_type="1h",
    )
    defaults.update(kw)
    return EvalConfig(**defaults)


def test_run_evaluation_returns_report_and_trace(bars_factory):
    report, records = run_evaluation(_cfg(bars_factory(80, drift=0.002)))
    assert report["samples"] == 60  # 80 - window(20) = 60
    assert len(records) == 60
    required = {
        "index",
        "label",
        "jev_action",
        "jev_confidence",
        "source",
        "fallback_reason",
        "final_action",
        "confidence",
        "probabilities",
        "correct",
        "jev_cost_usd",
        "fallback_cost_usd",
        "sub_signals",
    }
    assert required <= set(records[0])
    assert all(r["final_action"] in ("buy", "sell", "hold") for r in records)
    assert set(report) >= {"samples", "metrics", "cost", "slices", "recommendation", "data_fingerprint"}
    assert report["advisory_only"] is True  # stub 数据结论仅供参考


def test_extreme_thresholds_force_all_fallback(bars_factory):
    report, records = run_evaluation(
        # 阈值超过置信度上界 1.0，任何 Jev 直出都被门控拦下
        _cfg(bars_factory(80, drift=0.002), open_threshold=1.01, hold_threshold=1.01)
    )
    assert all(r["source"] == "fallback" for r in records)
    assert report["cost"]["fallback_calls"] == 60


def test_slices_are_sixty_forty_time_split(bars_factory):
    report, _ = run_evaluation(_cfg(bars_factory(80, drift=0.002)))
    train, test = report["slices"]["train"], report["slices"]["test"]
    assert train["samples"] == 36
    assert test["samples"] == 24
    assert "accuracy" in train and "ece" in train and "cost" in train


def test_recommendation_none_below_min_samples(bars_factory):
    # 25 根 → 5 个样本，远低于 min_samples=50，不得给阈值建议
    report, _ = run_evaluation(_cfg(bars_factory(25, drift=0.002), min_samples=50))
    assert report["recommendation"] is None


def test_csv_sha256_echoed(bars_factory, tmp_path):
    csv_path = tmp_path / "bars.csv"
    bars_factory(80, drift=0.002).to_csv(csv_path, index=False)
    report, _ = run_evaluation(_cfg(pd.read_csv(csv_path), csv_path=csv_path))
    expected = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    assert report["data_fingerprint"]["csv_sha256"] == expected

    report2, _ = run_evaluation(_cfg(bars_factory(80, drift=0.002)))
    assert report2["data_fingerprint"]["csv_sha256"] is None
