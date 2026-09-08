"""worker/lifecycle.py 自动迭代生命周期的单测。

覆盖：
- WorkerLifecycleConfig 默认值
- _should_retrain / _should_optimize 阈值判定
- _evaluate_current 恒为全 0
- stop / run 循环（patch time.sleep 与迭代方法后单次退出）
- _rl_iteration / _rule_iteration 的“评估→重训/优化→比较→部署”编排
- 函数内 import 的重依赖（optuna / RLService / BacktestDataProvider）patch 点

除被 mock 的对象外，不发起任何真实 IO 或训练。
"""

import sys
from unittest import mock

import pytest

import worker.lifecycle as lifecycle_mod
from worker.lifecycle import WorkerLifecycle, WorkerLifecycleConfig


class _FakeTime:
    """记录 sleep 调用的 time 替身。"""

    def __init__(self):
        self.sleep_calls = []

    def sleep(self, seconds):
        self.sleep_calls.append(seconds)


# --------------------------------------------------------------------------- #
# 配置默认值与基础构造
# --------------------------------------------------------------------------- #


def test_config_defaults():
    config = WorkerLifecycleConfig(worker_id=7)
    assert config.worker_id == 7
    assert config.strategy_type == "rule"
    assert config.check_interval_hours == 24
    assert config.max_retrain_age_days == 7
    assert config.min_sharpe == 0.5
    assert config.max_drawdown_pct == 5.0
    assert config.retrain_timesteps == 10000
    assert config.hpo_trials == 20
    assert config.hpo_timesteps == 5000


def test_worker_constructs_with_valid_worker_id():
    wl = WorkerLifecycle(WorkerLifecycleConfig(worker_id=42))
    assert wl.config.worker_id == 42
    assert wl._running is False


def test_stop_sets_running_false():
    wl = WorkerLifecycle(WorkerLifecycleConfig(worker_id=1))
    wl._running = True
    wl.stop()
    assert wl._running is False


# --------------------------------------------------------------------------- #
# 阈值判定
# --------------------------------------------------------------------------- #


def test_should_retrain_trades_below_threshold():
    wl = WorkerLifecycle(WorkerLifecycleConfig(worker_id=1))
    assert wl._should_retrain({"trades": 9, "sharpe": 2.0, "drawdown": 0.0}) is True


def test_should_retrain_sharpe_below_threshold():
    wl = WorkerLifecycle(WorkerLifecycleConfig(worker_id=1))
    assert wl._should_retrain({"trades": 10, "sharpe": 0.4, "drawdown": 0.0}) is True


def test_should_retrain_drawdown_exceeds_max():
    wl = WorkerLifecycle(WorkerLifecycleConfig(worker_id=1))
    assert wl._should_retrain({"trades": 10, "sharpe": 0.6, "drawdown": 6.0}) is True


def test_should_retrain_above_thresholds_false():
    wl = WorkerLifecycle(WorkerLifecycleConfig(worker_id=1))
    assert wl._should_retrain({"trades": 10, "sharpe": 0.6, "drawdown": 2.0}) is False


def test_should_optimize_delegates_to_should_retrain():
    wl = WorkerLifecycle(WorkerLifecycleConfig(worker_id=1))
    metrics = {"trades": 3, "sharpe": 0.0, "drawdown": 0.0}
    with mock.patch.object(wl, "_should_retrain", return_value=True) as mocked:
        assert wl._should_optimize(metrics) is True
    mocked.assert_called_once_with(metrics)


# --------------------------------------------------------------------------- #
# 评估 / 迭代编排
# --------------------------------------------------------------------------- #


def test_evaluate_current_returns_zeros():
    wl = WorkerLifecycle(WorkerLifecycleConfig(worker_id=1))
    assert wl._evaluate_current() == {"pnl": 0.0, "sharpe": 0.0, "trades": 0, "drawdown": 0.0}


def test_run_single_iteration_and_exit_without_sleep(monkeypatch):
    fake_time = _FakeTime()
    monkeypatch.setattr(lifecycle_mod, "time", fake_time)
    wl = WorkerLifecycle(WorkerLifecycleConfig(worker_id=1))
    iteration = mock.MagicMock(side_effect=wl.stop)
    monkeypatch.setattr(wl, "_iteration", iteration)
    wl.run()
    assert iteration.call_count == 1
    assert fake_time.sleep_calls == []
    assert wl._running is False


def test_run_sleeps_between_iterations_until_stop(monkeypatch):
    fake_time = _FakeTime()
    monkeypatch.setattr(lifecycle_mod, "time", fake_time)
    wl = WorkerLifecycle(WorkerLifecycleConfig(worker_id=2, check_interval_hours=3))
    calls = {"count": 0}

    def _fake_iteration():
        calls["count"] += 1
        if calls["count"] == 2:
            wl.stop()

    monkeypatch.setattr(wl, "_iteration", _fake_iteration)
    wl.run()
    assert calls["count"] == 2
    assert fake_time.sleep_calls == [3 * 3600]


def test_rl_iteration_retrains_and_deploys_when_new_better(monkeypatch):
    wl = WorkerLifecycle(WorkerLifecycleConfig(worker_id=1))
    current = {"pnl": 5.0, "sharpe": 0.5, "trades": 3, "drawdown": 1.0}
    new = {"pnl": 9.0, "sharpe": 1.2, "trades": 15, "drawdown": 0.5}
    monkeypatch.setattr(wl, "_evaluate_current", lambda: current)
    monkeypatch.setattr(wl, "_retrain", lambda: "model_worker_1_v2")
    monkeypatch.setattr(wl, "_evaluate_model", lambda model: new)
    deploy = mock.MagicMock()
    monkeypatch.setattr(wl, "_deploy", deploy)
    wl._rl_iteration()
    deploy.assert_called_once_with("model_worker_1_v2")


def test_rl_iteration_keeps_old_model_when_new_not_better(monkeypatch):
    wl = WorkerLifecycle(WorkerLifecycleConfig(worker_id=1))
    current = {"pnl": 5.0, "sharpe": 0.5, "trades": 3, "drawdown": 1.0}
    new = {"pnl": 3.0, "sharpe": 0.3, "trades": 8, "drawdown": 2.0}
    monkeypatch.setattr(wl, "_evaluate_current", lambda: current)
    monkeypatch.setattr(wl, "_retrain", lambda: "model_worker_1_v2")
    monkeypatch.setattr(wl, "_evaluate_model", lambda model: new)
    deploy = mock.MagicMock()
    monkeypatch.setattr(wl, "_deploy", deploy)
    wl._rl_iteration()
    deploy.assert_not_called()


def test_rule_iteration_deploys_when_new_params_better(monkeypatch):
    wl = WorkerLifecycle(WorkerLifecycleConfig(worker_id=1))
    current = {"pnl": 5.0, "sharpe": 0.5, "trades": 3, "drawdown": 1.0}
    params = {"fast": 5, "slow": 20}
    new = {"pnl": 8.0, "sharpe": 1.2, "trades": 12, "drawdown": 0.5}
    monkeypatch.setattr(wl, "_evaluate_current", lambda: current)
    monkeypatch.setattr(wl, "_optimize_params", lambda: params)
    monkeypatch.setattr(wl, "_evaluate_params", lambda p: new)
    deploy = mock.MagicMock()
    monkeypatch.setattr(wl, "_deploy_params", deploy)
    wl._rule_iteration()
    deploy.assert_called_once_with(params)


def test_rule_iteration_keeps_when_new_params_not_better(monkeypatch):
    wl = WorkerLifecycle(WorkerLifecycleConfig(worker_id=1))
    current = {"pnl": 5.0, "sharpe": 0.5, "trades": 3, "drawdown": 1.0}
    params = {"fast": 5, "slow": 20}
    new = {"pnl": 1.0, "sharpe": 0.2, "trades": 2, "drawdown": 4.0}
    monkeypatch.setattr(wl, "_evaluate_current", lambda: current)
    monkeypatch.setattr(wl, "_optimize_params", lambda: params)
    monkeypatch.setattr(wl, "_evaluate_params", lambda params: new)
    deploy = mock.MagicMock()
    monkeypatch.setattr(wl, "_deploy_params", deploy)
    wl._rule_iteration()
    deploy.assert_not_called()


# --------------------------------------------------------------------------- #
# 函数内 import 的依赖 patch 点
# --------------------------------------------------------------------------- #


def test_retrain_delegates_to_patched_rl_service(monkeypatch):
    result = mock.MagicMock()
    result.model_path = "/tmp/models/worker_3.pkl"
    rl_cls = mock.MagicMock()
    rl_cls.return_value.train.return_value = result
    cfg_cls = mock.MagicMock()
    monkeypatch.setattr("services.rl_service.RLService", rl_cls)
    monkeypatch.setattr("services.rl_service.RLTrainConfig", cfg_cls)

    wl = WorkerLifecycle(WorkerLifecycleConfig(worker_id=3))
    path = wl._retrain()
    assert path == "/tmp/models/worker_3.pkl"
    assert cfg_cls.call_args.kwargs["model_name"] == "worker_3"
    assert cfg_cls.call_args.kwargs["total_timesteps"] == wl.config.retrain_timesteps
    rl_cls.return_value.train.assert_called_once_with(cfg_cls.return_value)


def test_optimize_params_uses_patched_optuna(monkeypatch):
    study = mock.MagicMock()
    study.best_params = {"fast": 5, "slow": 20}
    fake_optuna = mock.MagicMock()
    fake_optuna.create_study.return_value = study
    monkeypatch.setitem(sys.modules, "optuna", fake_optuna)

    wl = WorkerLifecycle(WorkerLifecycleConfig(worker_id=1))
    result = wl._optimize_params()
    assert result == {"fast": 5, "slow": 20}
    fake_optuna.create_study.assert_called_once_with(direction="maximize")
    assert study.optimize.call_args.kwargs["n_trials"] == wl.config.hpo_trials


def test_load_market_data_uses_patched_backtest_provider(monkeypatch):
    provider_cls = mock.MagicMock()
    monkeypatch.setattr("backtest.data_provider.BacktestDataProvider", provider_cls)
    wl = WorkerLifecycle(WorkerLifecycleConfig(worker_id=1))
    df = wl._load_market_data("ETHUSDT", "1h")
    provider_cls.return_value.load_klines.assert_called_once_with("ETHUSDT", "1h")
    assert df is provider_cls.return_value.load_klines.return_value
