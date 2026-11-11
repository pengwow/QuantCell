"""Tests for rl/evaluation.py — 门面转发与 EvaluationMetrics 契约。

指标数值口径（sharpe √252 / profit_factor 999.99 哨兵 / 早退零值等）已随设施
下沉 axon_quant，由 axon_quant 的 tests/python/test_rl_evaluation.py 守护；
这里只测 backend 保留的契约：dataclass 默认值 + 门面把 SB3 predict 的
action 正确交给 env 并转回 dataclass。
"""

from rl.evaluation import EvaluationMetrics, evaluate_model


def test_evaluate_metrics_dataclass():
    """EvaluationMetrics defaults."""
    m = EvaluationMetrics()
    assert m.total_pnl == 0.0
    assert m.sharpe_ratio == 0.0
    assert m.num_trades == 0


def test_evaluate_model_unwraps_predict_action():
    """SB3 predict 返回 (action, state)；门面必须拆包后把 action 交给 env.step。"""

    class FixedModel:
        def predict(self, obs, deterministic=True):
            assert deterministic is True
            return "buy", None

    class OneStepEnv:
        def reset(self):
            return None, {"portfolio_value": 100.0}

        def step(self, action):
            assert action == "buy"  # (action, state) tuple 漏下去会破坏 env 协议
            return None, 0.0, True, False, {"portfolio_value": 105.0, "trades_executed": 2}

    m = evaluate_model(FixedModel(), OneStepEnv(), transaction_cost=2.0)
    assert isinstance(m, EvaluationMetrics)
    assert m.total_pnl == 5.0
    assert m.num_trades == 2
    assert m.turnover == 0.0  # env 未给 transaction_costs → 反推无效记 0
