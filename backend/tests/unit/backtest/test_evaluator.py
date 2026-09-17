"""BacktestEvaluator — 真实回测 HPO evaluator 单元测试。

全部走真 EventDrivenBacktestEngine + DualMA 策略,不用 mock。
"""

import math
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from axon_bridge import swap_instrument
from backtest.evaluator import BacktestEvaluator
from backtest.hpo_runner import HPORunner

# ── fixtures ──────────────────────────────────────────────────────


@pytest.fixture()
def sample_csv(tmp_path) -> str:
    """生成一份小样本 CSV (200 bar, 1h) 给 evaluator 用。"""
    n = 200
    dates = pd.date_range("2025-01-01", periods=n, freq="1h")
    rng = np.random.default_rng(42)
    closes = 100 + np.cumsum(rng.normal(0.05, 0.5, n))
    df = pd.DataFrame(
        {
            "open": closes - 0.3,
            "high": closes + 0.5,
            "low": closes - 0.5,
            "close": closes,
            "volume": rng.uniform(100, 1000, n),
        },
        index=dates,
    )
    df.index.name = "timestamp"
    p = tmp_path / "sample.csv"
    df.to_csv(p)
    return str(p)


@pytest.fixture()
def instrument_dict():
    return swap_instrument("BTC", "USDT", settle="usd_margin", contract_size=1.0)


@pytest.fixture()
def engine_config():
    return {
        "initial_capital": 100_000.0,
        "start_date": "2025-01-01",
        "end_date": "2025-01-10",
        "half_spread": 0.001,
        "depth_levels": 4,
        "size_per_level": 50.0,
        "auto_rebalance_threshold": 0.001,
    }


@pytest.fixture()
def make_dual_ma_builder():
    """返回 DualMA 策略 builder — 接收 params dict,返回策略实例。"""

    def _build(params):
        import sys

        sys.path.insert(0, "strategies")
        from strategies.dual_ma import DualMA, DualMAConfig

        return DualMA(
            DualMAConfig(
                instrument_ids=["BTCUSDT"],
                bar_types=["1h"],
                fast_period=int(params["fast"]),
                slow_period=int(params["slow"]),
                trade_size=Decimal("1.0"),
            )
        )

    return _build


# ── 构造函数:必填项预检 ────────────────────────────────────────────


def test_rejects_missing_required_config_keys(sample_csv, instrument_dict):
    """engine_config 缺少 initial_capital / start_date / end_date 时入口拒绝。"""
    bad_cfg = {"initial_capital": 100_000.0}  # 缺 start_date/end_date
    with pytest.raises(ValueError, match="缺少必需字段"):
        BacktestEvaluator(
            csv_path=sample_csv,
            instrument_dict=instrument_dict,
            instrument_id="BTCUSDT",
            engine_config=bad_cfg,
        )


def test_rejects_nonexistent_csv(tmp_path, instrument_dict, engine_config):
    p = str(tmp_path / "not_exists.csv")
    with pytest.raises(FileNotFoundError):
        BacktestEvaluator(
            csv_path=p,
            instrument_dict=instrument_dict,
            instrument_id="BTCUSDT",
            engine_config=engine_config,
        )


def test_accepts_all_required_fields(sample_csv, instrument_dict, engine_config):
    ev = BacktestEvaluator(
        csv_path=sample_csv,
        instrument_dict=instrument_dict,
        instrument_id="BTCUSDT",
        engine_config=engine_config,
    )
    assert ev.initial_cash == 100_000.0


def test_initial_cash_defaults_from_engine_config(sample_csv, instrument_dict, engine_config):
    """initial_cash 没传时从 engine_config.initial_capital 回退。"""
    ev = BacktestEvaluator(
        csv_path=sample_csv,
        instrument_dict=instrument_dict,
        instrument_id="BTCUSDT",
        engine_config=engine_config,
    )
    assert ev.initial_cash == engine_config["initial_capital"]


# ── make_objective:返回签名 + metric 合法性 ────────────────────────


def test_make_objective_rejects_unknown_metric(sample_csv, instrument_dict, engine_config, make_dual_ma_builder):
    ev = BacktestEvaluator(
        csv_path=sample_csv,
        instrument_dict=instrument_dict,
        instrument_id="BTCUSDT",
        engine_config=engine_config,
    )
    with pytest.raises(ValueError, match="不支持的指标"):
        ev.make_objective(make_dual_ma_builder, metric="unknown_metric")


def test_make_objective_returns_callable_with_two_params(
    sample_csv, instrument_dict, engine_config, make_dual_ma_builder
):
    import inspect

    ev = BacktestEvaluator(
        csv_path=sample_csv,
        instrument_dict=instrument_dict,
        instrument_id="BTCUSDT",
        engine_config=engine_config,
    )
    fn = ev.make_objective(make_dual_ma_builder)
    sig = inspect.signature(fn)
    assert len(sig.parameters) == 2  # (params, report)


# ── 单次 evaluate:真引擎跑通 ──────────────────────────────────────


def test_evaluate_returns_finite_return(sample_csv, instrument_dict, engine_config, make_dual_ma_builder):
    """单次 evaluate 走完真实回测,返回的收益率是有限数。"""
    import logging

    logging.getLogger("strategies.dual_ma").setLevel(logging.WARNING)

    ev = BacktestEvaluator(
        csv_path=sample_csv,
        instrument_dict=instrument_dict,
        instrument_id="BTCUSDT",
        engine_config=engine_config,
    )
    fn = ev.make_objective(make_dual_ma_builder, metric="return")

    # 伪 report:捕获被上报的 step/value
    reported: list[tuple[int, float]] = []

    def report(step: int, value: float) -> None:
        reported.append((step, value))

    score = fn({"fast": 5, "slow": 15}, report)
    assert math.isfinite(score), f"score 应为有限数,实得 {score}"
    # bar_nav_curve 至少有 2 个点(初始 + 结束),report 至少被调过几次
    assert len(reported) >= 2


def test_evaluate_with_different_metrics(sample_csv, instrument_dict, engine_config, make_dual_ma_builder):
    """return / final_nav / total_pnl / sharpe / win_rate 都能取到有限值。"""
    import logging

    logging.getLogger("strategies.dual_ma").setLevel(logging.WARNING)

    ev = BacktestEvaluator(
        csv_path=sample_csv,
        instrument_dict=instrument_dict,
        instrument_id="BTCUSDT",
        engine_config=engine_config,
    )

    for metric in ["return", "final_nav", "total_pnl", "sharpe", "win_rate"]:
        fn = ev.make_objective(make_dual_ma_builder, metric=metric)
        score = fn({"fast": 5, "slow": 15}, lambda s, v: None)
        assert math.isfinite(score), f"{metric} 应为有限数,实得 {score}"


# ── 完整 HPO 闭环:HPORunner + BacktestEvaluator ────────────────────


def test_full_hpo_loop_with_real_backtest(sample_csv, instrument_dict, engine_config, make_dual_ma_builder):
    """HPORunner + BacktestEvaluator 端到端:3 trials,全 complete,best_params 存在。"""
    import logging

    logging.getLogger("strategies.dual_ma").setLevel(logging.WARNING)

    ev = BacktestEvaluator(
        csv_path=sample_csv,
        instrument_dict=instrument_dict,
        instrument_id="BTCUSDT",
        engine_config=engine_config,
    )
    objective = ev.make_objective(make_dual_ma_builder, metric="return")

    result = HPORunner().optimize(
        objective_fn=objective,
        param_space={
            "fast": {"type": "int", "low": 3, "high": 10},
            "slow": {"type": "int", "low": 15, "high": 30},
        },
        n_trials=3,
        seed=42,
        study_name="evaluator_full_loop",
    )

    assert result["best_params"] is not None, "应有最优参数"
    assert math.isfinite(result["best_value"]), "最优值应有限"
    assert len(result["trials"]) == 3
    # 每个 complete trial 至少有 2 个 intermediate_values
    for t in result["trials"]:
        assert t["state"] == "complete"
        assert len(t.get("intermediate_values", {})) >= 2


def test_validate_params_hook_allows_subclass_to_reject(tmp_path, instrument_dict, engine_config, make_dual_ma_builder):
    """子类 override _validate_params 可以跳过引擎启动直接返回 -inf。

    场景:DualMA 在 fast>=slow 时不会崩,只是表现很差,默认 evaluator 让它跑。
    但子类可以加规则拦截,省掉引擎启动开销。
    """
    import logging

    n = 50
    df = pd.DataFrame(
        {
            "open": 100 + np.random.randn(n),
            "high": 101 + np.random.randn(n),
            "low": 99 + np.random.randn(n),
            "close": 100 + np.random.randn(n),
            "volume": np.random.uniform(100, 1000, n),
        },
        index=pd.date_range("2025-01-01", periods=n, freq="1h"),
    )
    df.index.name = "timestamp"
    p = tmp_path / "small.csv"
    df.to_csv(p)

    logging.getLogger("strategies.dual_ma").setLevel(logging.WARNING)

    # ---- 默认 evaluator ----
    ev_default = BacktestEvaluator(
        csv_path=str(p),
        instrument_dict=instrument_dict,
        instrument_id="BTCUSDT",
        engine_config=engine_config,
    )
    fn_default = ev_default.make_objective(make_dual_ma_builder)

    # fast >= slow 时 DualMA 不会崩,默认 evaluator 让它跑完
    bad_score = fn_default({"fast": 20, "slow": 5}, lambda s, v: None)
    assert math.isfinite(bad_score), "默认 evaluator 应放行非法参数(让策略跑完,结果差但不崩)"

    # ---- 带校验的子类 ----
    class _ValidatedEvaluator(BacktestEvaluator):
        def _validate_params(self, params: dict) -> bool:
            fast = int(params.get("fast", 0))
            slow = int(params.get("slow", 0))
            return fast < slow

    ev = _ValidatedEvaluator(
        csv_path=str(p),
        instrument_dict=instrument_dict,
        instrument_id="BTCUSDT",
        engine_config=engine_config,
    )
    fn = ev.make_objective(make_dual_ma_builder)

    # fast >= slow 被拦截,直接 -inf,根本不启动引擎
    assert fn({"fast": 20, "slow": 5}, lambda s, v: None) == float("-inf")
    # 合法参数仍然跑通
    assert math.isfinite(fn({"fast": 5, "slow": 15}, lambda s, v: None))
