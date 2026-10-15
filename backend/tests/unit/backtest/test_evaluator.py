"""BacktestEvaluator 单路径测试：合成 DataFrame + 模板 DualMA + BacktestLoop。

不再依赖 CSV 落盘与事件引擎，全部走唯一 BacktestLoop 路径。
"""

from __future__ import annotations

import math

import optuna
import pandas as pd

from backtest.evaluator import BacktestEvaluator
from strategy.base import StrategyConfig
from strategy.templates.dual_ma import DualMA


def _make_ohlcv(n: int = 120, seed: float = 100.0) -> pd.DataFrame:
    """趋势 + 周期波动的价格序列，保证 fast/slow 均线能产生交叉。"""
    idx = pd.date_range("2025-01-01", periods=n, freq="1h", tz="UTC")
    close = seed + pd.Series(range(n), dtype="float64") + 8.0 * pd.Series(range(n)).mod(12).astype("float64")
    return pd.DataFrame(
        {
            "open": close - 0.5,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 1000.0,
        },
        index=idx,
    )


def _build_strategy(params: dict):
    # 模板 DualMA 用共享 StrategyConfig，参数走 params dict（fast/slow）
    return DualMA(
        StrategyConfig(
            name="dual_ma",
            symbol="BTCUSDT",
            params={"fast": int(params["fast"]), "slow": int(params["slow"])},
        )
    )


def _make_evaluator(**overrides) -> BacktestEvaluator:
    kwargs: dict = dict(
        data=_make_ohlcv(),
        symbol="BTCUSDT",
        build_strategy=_build_strategy,
        param_space={"fast": (3, 10), "slow": (15, 40)},
        initial_cash=100_000.0,
    )
    kwargs.update(overrides)
    return BacktestEvaluator(**kwargs)


def test_evaluate_returns_finite_metric():
    """单次 evaluate 走完 BacktestLoop，返回有限 metric。"""
    metric = _make_evaluator().evaluate({"fast": 5, "slow": 20})
    assert isinstance(metric, float)
    assert math.isfinite(metric)


def test_evaluate_reports_equity_curve():
    """旧 evaluator 的 bar_nav_curve 中间值上报能力等价保留：
    evaluate 接收可选 report 闭包，跑完后从 equity_curve 逐点上报。"""
    reported: list[tuple[int, float]] = []
    metric = _make_evaluator().evaluate(
        {"fast": 5, "slow": 20},
        report=lambda step, value: reported.append((step, value)),
    )
    assert math.isfinite(metric)
    assert len(reported) >= 2  # 至少初始 + 结束两个点
    assert reported[0][0] == 0
    assert reported[-1][0] == len(reported) - 1
    assert all(math.isfinite(v) for _, v in reported)


def test_study_optimizes_via_objective():
    """optuna 原生 study 用 evaluator.objective 跑完多 trial 并选参。"""
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    evaluator = _make_evaluator()
    study = optuna.create_study(direction="maximize")
    study.optimize(evaluator.objective, n_trials=2)
    assert len(study.trials) == 2
    assert all(t.value is not None and math.isfinite(t.value) for t in study.trials)
