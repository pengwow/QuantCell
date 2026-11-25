"""Task 11：HPO trial 进程池执行 —— 一致性与执行器契约。

核心不变量：采样留在调用进程串行推进，trial 只是换了执行位置；固定 seed 下
进程池路径与串行路径的 trials 必须逐值一致。
"""

from __future__ import annotations

import pytest

from jobs.spec import JobResult, JobSpec


class _FakePool:
    """替身进程池：同步回调，记录投递的 spec，行为等价于即时完成。"""

    def __init__(self, compute) -> None:
        self.specs = []
        self._compute = compute

    def submit(self, spec, on_done):
        self.specs.append(spec)
        on_done(spec.job_id, self._compute(spec))
        return spec.job_id


def test_pool_trial_executor_matches_serial_trials(monkeypatch):
    """固定 seed 下，进程池路径与串行路径 trials 逐值一致（Task 11.2）。"""
    from backtest.hpo_runner import HPORunner
    from jobs import hpo_trial_job

    def score(params: dict) -> float:
        return float(params["a"] * 10 + params["b"])

    def serial_objective(params: dict, report) -> float:
        value = score(params)
        report(1, value / 2)  # 中间值：验证进程池侧回放等价
        return value

    def compute(spec: JobSpec) -> JobResult:
        value = score(spec.payload["params"])
        return JobResult(
            status="succeeded",
            result_ref=spec.job_id,
            metrics={"value": value, "intermediate": [[1, value / 2]]},
        )

    pool = _FakePool(compute)
    monkeypatch.setattr(hpo_trial_job, "_job_pool", lambda: pool)

    param_space = {
        "a": {"type": "int", "low": 0, "high": 5},
        "b": {"type": "int", "low": 0, "high": 5},
    }
    serial = HPORunner().optimize(
        objective_fn=serial_objective,
        param_space=param_space,
        n_trials=4,
        seed=11,
        study_name="parity_serial",
    )
    pooled = HPORunner().optimize(
        objective_fn=None,
        param_space=param_space,
        n_trials=4,
        seed=11,
        study_name="parity_pool",
        trial_executor=hpo_trial_job.PoolTrialExecutor({"symbol": "BTCUSDT", "interval": "15m"}),
    )

    assert len(pool.specs) == 4, "每个 trial 都应投递到进程池"
    assert {spec.kind for spec in pool.specs} == {hpo_trial_job.KIND}
    for spec in pool.specs:
        assert set(spec.payload) == {"symbol", "interval", "params"}

    def _strip(trials):
        return [{k: v for k, v in t.items() if k != "duration_ms"} for t in trials]

    assert _strip(pooled["trials"]) == _strip(serial["trials"])
    assert pooled["best_params"] == serial["best_params"]
    assert pooled["best_value"] == serial["best_value"]


def test_pool_trial_executor_parses_outcome(monkeypatch):
    """执行器把 JobResult.metrics 还原成 (value, 中间值)。"""
    from jobs import hpo_trial_job

    pool = _FakePool(
        lambda spec: JobResult(
            status="succeeded",
            result_ref=spec.job_id,
            metrics={"value": 1.5, "intermediate": [[0, 1.0], [1, 2.0]]},
        )
    )
    monkeypatch.setattr(hpo_trial_job, "_job_pool", lambda: pool)

    executor = hpo_trial_job.PoolTrialExecutor({"symbol": "BTCUSDT", "interval": "15m"})
    value, intermediate = executor({"fast": 10, "slow": 30})

    assert value == 1.5
    assert intermediate == [(0, 1.0), (1, 2.0)]
    assert pool.specs[0].payload["params"] == {"fast": 10, "slow": 30}


def test_pool_trial_executor_raises_on_failed_trial(monkeypatch):
    """worker 失败时执行器抛 TrialExecutionError，由 optuna 记为该 trial 剪枝。"""
    from jobs import hpo_trial_job

    pool = _FakePool(lambda spec: JobResult(status="failed", error="boom"))
    monkeypatch.setattr(hpo_trial_job, "_job_pool", lambda: pool)

    executor = hpo_trial_job.PoolTrialExecutor({"symbol": "BTCUSDT", "interval": "15m"})
    with pytest.raises(hpo_trial_job.TrialExecutionError, match="boom"):
        executor({"fast": 10, "slow": 30})


class _HangingPool:
    """永不回调的池：模拟 trial 超时；cancel_queued 的返回值由 queued 决定。"""

    def __init__(self, queued: bool) -> None:
        self.specs = []
        self.cancelled = []
        self._queued = queued

    def submit(self, spec, on_done):
        self.specs.append(spec)
        return spec.job_id

    def cancel_queued(self, job_id: str) -> bool:
        self.cancelled.append(job_id)
        return self._queued


def test_timeout_cancels_queued_trial(monkeypatch):
    """超时时 trial 还在排队：直接从池里撤下，不再占 worker，也不写 stop 标志。"""
    from jobs import hpo_trial_job

    pool = _HangingPool(queued=True)
    monkeypatch.setattr(hpo_trial_job, "_job_pool", lambda: pool)
    stops = []
    monkeypatch.setattr(hpo_trial_job.progress_spool, "request_stop", lambda jid: stops.append(jid))

    executor = hpo_trial_job.PoolTrialExecutor({"symbol": "BTCUSDT", "interval": "15m"}, timeout_seconds=0.05)
    with pytest.raises(hpo_trial_job.TrialExecutionError, match="超时"):
        executor({"fast": 10, "slow": 30})

    assert pool.cancelled == [pool.specs[0].job_id]
    assert stops == []


def test_timeout_marks_stop_for_dispatched_trial(monkeypatch):
    """超时时 trial 已派发：写 stop 标志，worker 入口看到即退。"""
    from jobs import hpo_trial_job

    pool = _HangingPool(queued=False)
    monkeypatch.setattr(hpo_trial_job, "_job_pool", lambda: pool)
    stops = []
    monkeypatch.setattr(hpo_trial_job.progress_spool, "request_stop", lambda jid: stops.append(jid))

    executor = hpo_trial_job.PoolTrialExecutor({"symbol": "BTCUSDT", "interval": "15m"}, timeout_seconds=0.05)
    with pytest.raises(hpo_trial_job.TrialExecutionError, match="超时"):
        executor({"fast": 10, "slow": 30})

    assert pool.cancelled == [pool.specs[0].job_id]
    assert stops == [pool.specs[0].job_id]


def test_run_hpo_trial_job_exits_early_when_stop_requested(monkeypatch):
    """排队期间被撤销的 trial 出队即退，不再跑完整回测。"""
    from jobs import hpo_trial_job

    monkeypatch.setattr(hpo_trial_job.progress_spool, "stop_requested", lambda jid: True)
    spec = JobSpec(job_id="hpo-cancelled", kind=hpo_trial_job.KIND, payload={"params": {}})
    result = hpo_trial_job.run_hpo_trial_job(spec)
    assert result.status == "interrupted"


def test_evaluate_trial_payload_penalizes_invalid_params():
    """非法参数直接记 -inf，与 BacktestEvaluator 惩罚口径一致（不加载数据）。"""
    from jobs.hpo_trial_job import evaluate_trial_payload

    outcome = evaluate_trial_payload({"symbol": "BTCUSDT", "interval": "15m", "params": {"fast": 30, "slow": 10}})
    assert outcome == {"value": float("-inf"), "intermediate": []}
