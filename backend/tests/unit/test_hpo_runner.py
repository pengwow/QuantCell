"""Tests for backtest/hpo_runner.py — HPORunner."""


def test_hpo_runner_creation():
    """HPORunner可以被创建"""
    from backtest.hpo_runner import HPORunner

    hpo = HPORunner()
    assert hpo is not None


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
