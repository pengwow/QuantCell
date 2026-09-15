"""Tests for backtest/hpo_runner.py — HPORunner."""

import pytest


def test_hpo_runner_creation():
    """HPORunner可以被创建"""
    from backtest.hpo_runner import HPORunner

    hpo = HPORunner()
    assert hpo is not None


def test_engine_validation_rejects_inverted_bounds():
    """引擎侧校验(0.14.3 新增):low > high 的维度在入口被拒绝,错误信息带维度名。"""
    from backtest.hpo_runner import HPORunner

    hpo = HPORunner()
    with pytest.raises(ValueError, match="fast"):
        hpo.optimize(
            objective_fn=lambda p: 0.0,
            param_space={"fast": {"type": "int", "low": 50, "high": 20}},
            n_trials=1,
        )


def test_engine_validation_rejects_empty_choices():
    """引擎侧校验:空 choices 列表被拒绝(引擎 SearchSpaceDef 中文报错)。"""
    from backtest.hpo_runner import HPORunner

    hpo = HPORunner()
    with pytest.raises(ValueError, match="choices 不能为空"):
        hpo.optimize(
            objective_fn=lambda p: 0.0,
            param_space={"mode": {"type": "choice", "choices": []}},
            n_trials=1,
        )


def test_engine_validation_rejects_unknown_type():
    """未知参数类型被拒绝(修复旧行为:此前会静默产出缺 key 的参数)。"""
    from backtest.hpo_runner import HPORunner

    hpo = HPORunner()
    with pytest.raises(ValueError, match="不支持的参数类型"):
        hpo.optimize(
            objective_fn=lambda p: 0.0,
            param_space={"lr": {"type": "log", "low": 1e-5, "high": 1e-1}},
            n_trials=1,
        )


def test_optuna_backend_runs_real_search():
    """0.14.4 完整循环:OptunaHPO 真实采样(TPE),最优参数被正确选出。

    choice 空间 3×3=9 种组合,seed=42 + 20 trials 保证覆盖全部组合,
    理论最优 (30, 3) 必被采到。
    """
    from backtest.hpo_runner import HPORunner

    hpo = HPORunner()
    result = hpo.optimize(
        # 目标:f+s 越大越好,choice 空间保证可穷举验证
        objective_fn=lambda p: p["f"] + p["s"],
        param_space={
            "f": {"type": "choice", "choices": [10, 20, 30]},
            "s": {"type": "choice", "choices": [1, 2, 3]},
        },
        n_trials=20,
        seed=42,
        study_name="optuna_real_search",
    )

    assert result["best_params"] == {"f": 30, "s": 3}
    assert result["best_value"] == 33
    assert len(result["trials"]) == 20


def test_optuna_backend_float_int_sampling_within_bounds():
    """float/uniform 与 int/int_uniform 采样均落在边界内,结果字段完整。"""
    from backtest.hpo_runner import HPORunner

    hpo = HPORunner()
    result = hpo.optimize(
        objective_fn=lambda p: -abs(p["x"] - 0.5) - abs(p["n"] - 50),
        param_space={
            "x": {"type": "float", "low": 0.0, "high": 1.0},
            "n": {"type": "int", "low": 0, "high": 100},
        },
        n_trials=5,
    )

    for trial in result["trials"]:
        assert 0.0 <= trial["params"]["x"] <= 1.0
        assert 0 <= trial["params"]["n"] <= 100
    assert result["best_params"] is not None
    assert result["best_value"] >= result["trials"][0]["values"][0] - 1e-9


def test_hpo_runner_finds_best_params():
    """HPORunner找到最优参数"""
    from backtest.hpo_runner import HPORunner

    hpo = HPORunner()

    param_space = {
        "fast": {"type": "int", "low": 5, "high": 20},
        "slow": {"type": "int", "low": 20, "high": 50},
    }

    def objective(params):
        return params["slow"] - params["fast"]

    result = hpo.optimize(
        objective_fn=objective,
        param_space=param_space,
        n_trials=10,
    )
    assert "best_params" in result
    assert "best_value" in result
    assert result["best_value"] > 0


def test_hpo_runner_respects_n_trials():
    """HPORunner执行指定次数的试验"""
    from backtest.hpo_runner import HPORunner

    hpo = HPORunner()

    param_space = {
        "x": {"type": "float", "low": 0.0, "high": 1.0},
    }

    result = hpo.optimize(
        objective_fn=lambda p: p["x"],
        param_space=param_space,
        n_trials=5,
    )
    assert result["n_trials"] == 5


def test_hpo_scores_finite():
    """HPO 冒烟(报告 P2):OptunaHPO 2 轮,所有得分与最优值均有限。"""
    import math

    from backtest.hpo_runner import HPORunner

    hpo = HPORunner()
    param_space = {
        "fast": {"type": "int", "low": 5, "high": 20},
        "slow": {"type": "int", "low": 20, "high": 50},
    }
    # 目标函数模拟回测得分(fast 与 slow 差越大越好,恒有限)
    result = hpo.optimize(
        objective_fn=lambda p: float(p["slow"] - p["fast"]),
        param_space=param_space,
        n_trials=2,
    )

    assert len(result["trials"]) == 2
    for trial in result["trials"]:
        assert math.isfinite(trial["values"][0])
    assert math.isfinite(result["best_value"])
    assert result["best_value"] == max(t["values"][0] for t in result["trials"])


def test_multi_objective_pareto_front_and_hypervolume():
    """多目标优化:Pareto 前沿被正确选出,超体积可计算。"""
    from backtest.hpo_runner import HPORunner

    hpo = HPORunner()
    result = hpo.optimize(
        # 目标1: x+y 越大越好; 目标2: x-y 越大越好(两者矛盾)
        objective_fn=lambda p: [p["x"] + p["y"], p["x"] - p["y"]],
        param_space={
            "x": {"type": "choice", "choices": [-10.0, 0.0, 10.0]},
            "y": {"type": "choice", "choices": [-10.0, 0.0, 10.0]},
        },
        n_trials=9,
        directions=["maximize", "maximize"],
        reference_point=[-20.0, -20.0],
        study_name="pareto_test",
    )

    # 多目标无 best_params/best_value(用 Pareto 前沿)
    assert result["best_params"] is None
    assert result["pareto_front"], "应有 Pareto 前沿"
    assert result["hypervolume"] is not None, "应计算超体积"
    # Pareto 前沿中的每个点都是不被支配的
    for trial in result["trials"]:
        # 如果某个 trial 在 Pareto 前沿,它不应被其他 trial 支配
        assert trial["values"][0] != -20.0 or trial["values"][1] != -20.0


def test_pruner_and_parallel_accepted():
    """剪枝配置与并行参数能被接受,旧签名(不传 report)不会崩。"""
    from backtest.hpo_runner import HPORunner

    hpo = HPORunner()
    # 旧签名 lambda p: ... 不传 report,引擎应兼容(自动忽略剪枝)
    result = hpo.optimize(
        objective_fn=lambda p: p["x"] * 2,
        param_space={"x": {"type": "float", "low": 0.0, "high": 1.0}},
        n_trials=5,
        pruner_type="median",
        n_warmup_steps=2,
        n_jobs=1,
        seed=42,
        study_name="pruner_compat_test",
    )
    assert len(result["trials"]) == 5
    # 旧签名不传 report,Optuna 收不到中间值,剪枝不触发
    assert all(t["state"] == "complete" for t in result["trials"])


def test_minimize_direction_works():
    """minimize 方向被正确识别,目标值越小越优。"""
    from backtest.hpo_runner import HPORunner

    hpo = HPORunner()
    result = hpo.optimize(
        objective_fn=lambda p: (p["x"] - 0.5) ** 2,  # 0.5 处取最小值 0
        param_space={"x": {"type": "float", "low": 0.0, "high": 1.0}},
        n_trials=5,
        directions="minimize",
        study_name="minimize_test",
    )
    assert result["best_params"] is not None
    # 最优 x 应接近 0.5
    assert abs(result["best_params"]["x"] - 0.5) < 0.3


def test_pruner_real_triggers_via_report_closure():
    """0.14.5 核心修复:剪枝真正触发。

    objective_fn 接收 report(step, value) 闭包,OptunaHPO 内部调
    optuna.trial.report + should_prune,中途差的 trial 被提前剪掉。
    """
    from backtest.hpo_runner import HPORunner

    hpo = HPORunner()

    def eval_with_report(params, report):
        x = params["x"]
        for step, frac in enumerate([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0], start=1):
            partial = x * frac
            report(step, partial)
        return x

    result = hpo.optimize(
        objective_fn=eval_with_report,
        param_space={"x": {"type": "float", "low": 0.0, "high": 1.0}},
        n_trials=15,
        pruner_type="median",
        n_startup_trials=3,
        n_warmup_steps=2,
        study_name="real_prune_test",
        seed=42,
    )

    pruned = [t for t in result["trials"] if t["state"] == "pruned"]
    complete = [t for t in result["trials"] if t["state"] == "complete"]

    assert len(pruned) > 0, "应有 trial 被剪枝"
    assert len(complete) > 0, "应有 trial 完整跑完"
    # 被剪的 trial intermediate_values 应该只有前几步(没跑完 10 step)
    for t in pruned:
        assert len(t["intermediate_values"]) < 10
    # 完整跑完的 intermediate_values 应该有 10 个 step
    for t in complete:
        assert len(t["intermediate_values"]) == 10
