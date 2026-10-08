"""纯函数评测指标：准确率、混淆矩阵/召回、ECE、成本汇总。"""

from __future__ import annotations

import pytest

from decision.evaluation.metrics import (
    accuracy,
    confusion_and_recall,
    cost_summary,
    expected_calibration_error,
)

LABELS = ("buy", "sell", "hold")


def _rec(pred: str, label: str, *, confidence: float = 0.8, jev_cost: float = 0.0, fb_cost: float = 0.0):
    """构造一条评测记录（source 由是否产生兜底成本推断）。"""
    return {
        "final_action": pred,
        "label": label,
        "confidence": confidence,
        "correct": pred == label,
        "source": "fallback" if fb_cost > 0 else "jev_direct",
        "jev_cost_usd": jev_cost,
        "fallback_cost_usd": fb_cost,
    }


def test_accuracy():
    records = [_rec("buy", "buy"), _rec("buy", "hold"), _rec("sell", "sell"), _rec("hold", "hold")]
    assert accuracy(records) == pytest.approx(0.75)
    assert accuracy([]) == 0.0


def test_confusion_matrix_and_recall():
    records = [
        _rec("buy", "buy"),
        _rec("buy", "hold"),
        _rec("sell", "sell"),
        _rec("hold", "hold"),
    ]
    matrix, recall = confusion_and_recall(records)
    # 行=预测，列=真实标签
    assert matrix["buy"] == {"buy": 1, "sell": 0, "hold": 1}
    assert matrix["sell"] == {"buy": 0, "sell": 1, "hold": 0}
    assert matrix["hold"] == {"buy": 0, "sell": 0, "hold": 1}
    # hold 真实 2 个、命中 1 个 → recall 0.5
    assert recall["buy"] == pytest.approx(1.0)
    assert recall["sell"] == pytest.approx(1.0)
    assert recall["hold"] == pytest.approx(0.5)


def test_ece_zero_for_perfectly_calibrated_bin():
    # confidence=0.0 且全部错误：箱内置信均值 0、正确率 0，ECE=0
    records = [_rec("hold", "buy", confidence=0.0) for _ in range(20)]
    assert expected_calibration_error(records) == pytest.approx(0.0)


def test_ece_none_when_any_populated_bin_too_small():
    # 非空箱只有 5 条（< min_bin_samples=10），ECE 不可信 → None
    records = [_rec("buy", "buy", confidence=0.9) for _ in range(5)]
    assert expected_calibration_error(records) is None


def test_cost_summary_separates_jev_and_fallback_spend():
    records = [
        _rec("buy", "buy", jev_cost=0.00003),  # 直出
        _rec("sell", "sell", jev_cost=0.00003),  # 直出
        _rec("hold", "hold", jev_cost=0.00003, fb_cost=0.002),  # 低置信兜底（Jev 已计费）
        _rec("hold", "buy", jev_cost=0.0, fb_cost=0.002),  # 异常兜底（Jev 未计费）
    ]
    summary = cost_summary(records)
    assert summary["samples"] == 4
    assert summary["jev_calls"] == 3
    assert summary["fallback_calls"] == 2
    assert summary["jev_direct_rate"] == pytest.approx(0.5)
    assert summary["total_jev_cost_usd"] == pytest.approx(0.00009)
    assert summary["total_fallback_cost_usd"] == pytest.approx(0.004)
    assert summary["total_cost_usd"] == pytest.approx(0.00409)
