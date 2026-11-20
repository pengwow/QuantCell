"""walk_forward_rl 训练窗/验证窗统计量对齐检查 + OOS 汇总测试。"""

from __future__ import annotations

import numpy as np
import pandas as pd

from rl.walk_forward_rl import (
    RLWalkForwardService,
    _aggregate_folds,
    _check_stats_alignment,
    _oos_report,
)


def _frame(returns: np.ndarray, start: float = 100.0) -> pd.DataFrame:
    closes = start * np.cumprod(1.0 + returns)
    return pd.DataFrame({"close": closes, "open": closes, "high": closes, "low": closes, "volume": 1.0})


def test_similar_windows_pass_alignment():
    rng = np.random.default_rng(42)
    train = _frame(rng.normal(0.0, 0.01, 500))
    valid = _frame(rng.normal(0.0, 0.01, 200))

    result = _check_stats_alignment(train, valid)

    assert result["passed"] is True
    assert result["reasons"] == []
    assert result["vol_ratio"] is not None


def test_bar_count_mismatch_fails_alignment():
    rng = np.random.default_rng(42)
    train = _frame(rng.normal(0.0, 0.01, 500))
    valid = _frame(rng.normal(0.0, 0.01, 5))

    result = _check_stats_alignment(train, valid)

    assert result["passed"] is False
    assert any("bar 数比异常" in reason for reason in result["reasons"])


def test_volatility_mismatch_fails_alignment():
    rng = np.random.default_rng(42)
    train = _frame(rng.normal(0.0, 0.0005, 500))
    valid = _frame(rng.normal(0.0, 0.05, 300))

    result = _check_stats_alignment(train, valid)

    assert result["passed"] is False
    assert any("波动率比异常" in reason for reason in result["reasons"])


def test_constant_price_windows_are_aligned():
    flat = pd.DataFrame({"close": [100.0] * 100})
    result = _check_stats_alignment(flat, flat.copy())
    assert result["passed"] is True


def test_missing_close_column_skips_metric_checks():
    train = pd.DataFrame({"foo": range(100)})
    valid = pd.DataFrame({"foo": range(100)})
    result = _check_stats_alignment(train, valid)
    # 无 close 列不造假指标;bar 数一致即放行
    assert result["passed"] is True
    assert result["train"]["mean_return"] is None


def test_validate_marks_fold_failed_and_continues():
    """对齐阈值设到不可能满足时,每折都进折级报告但不中断整轮。"""
    rng = np.random.default_rng(42)
    data = _frame(rng.normal(0.0, 0.01, 300))

    result = RLWalkForwardService().validate(
        data=data,
        env_factory=lambda _d: None,  # 对齐失败时不应构建环境
        algo_cls=object,
        n_splits=3,
        total_timesteps=10,
        stats_thresholds={"min_bar_ratio": 1.1},
    )

    assert len(result["folds"]) == 3
    for fold in result["folds"]:
        assert "统计量对齐失败" in fold["error"]
        assert fold["stats_check"]["passed"] is False
    assert result["aggregate"]["n_valid_folds"] == 0
    assert result["oos"]["evaluable"] is False
    assert result["oos"]["passed"] is None


def test_oos_report_passes_and_fails_on_aggregate_mean():
    passing = _aggregate_folds(
        [{"fold": 0, "oos_metrics": {"sharpe_ratio": 0.8, "total_return_pct": 1.2, "total_pnl": 100.0}}]
    )
    report = _oos_report(passing)
    assert report["evaluable"] is True
    assert report["passed"] is True
    assert report["metric_source"] == "walk_forward.aggregate.mean"

    failing = _aggregate_folds(
        [{"fold": 0, "oos_metrics": {"sharpe_ratio": -0.5, "total_return_pct": -2.0, "total_pnl": -100.0}}]
    )
    assert _oos_report(failing)["passed"] is False
