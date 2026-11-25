"""RL 训练入池的桥接测试（M2 Task 10）。

分两段：
- 父进程侧：投递字段、spool → TrainTask 还原、终态映射、取消写 `.stop`
- worker 侧：直接跑 `run_rl_train_job`（monkeypatch RLService.train），验证
  SpoolReporter 落盘契约与 JobResult 收敛
真实进程池不在这里起（spawn 子进程无法注入假训练），池本身的并行语义由
`tests/unit/jobs` 的 sleep 作业覆盖。
"""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

import jobs.progress_spool as spool
import jobs.rl_train_job as rl_train_job
import services.rl_service as rl_service_mod
from jobs.spec import JobResult, JobSpec
from services import rl_task_runner as runner


@pytest.fixture(autouse=True)
def _clean_state(tmp_path, monkeypatch):
    # spool 目录重定向到 tmp，别把测试进度文件写进 backend/data
    monkeypatch.setattr(spool, "_DATA_DIR", tmp_path)
    runner.reset_tasks()
    yield
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if all(s["status"] in runner.TERMINAL_STATUSES for s in runner.list_tasks()):
            break
        time.sleep(0.01)
    runner.reset_tasks()


class _FakePool:
    """只记录投递，不真起进程；用例手动触发 on_done。"""

    def __init__(self) -> None:
        self.submitted: list[tuple[JobSpec, object]] = []

    def submit(self, spec: JobSpec, on_done) -> None:
        self.submitted.append((spec, on_done))


def _task(task_id: str) -> runner.TrainTask:
    task = runner.get_task(task_id)
    assert task is not None
    return task


def test_submit_pool_job_relays_progress_and_terminal(monkeypatch):
    fake = _FakePool()
    monkeypatch.setattr(runner, "pool_enabled", lambda: True)
    monkeypatch.setattr(runner, "_job_pool", lambda: fake)

    task_id = runner.submit_train_task({"algorithm": "ppo", "total_timesteps": 64})
    assert _task(task_id).snapshot()["status"] == "queued"

    spec, on_done = fake.submitted[0]
    assert spec.kind == "rl_train"
    assert spec.job_id == task_id
    assert spec.payload["config"]["algorithm"] == "ppo"

    spool.write_snapshot(task_id, {"pid": 1, "stage": "learning", "progress": 0.4, "message": "训练中"})
    spool.append_event(task_id, {"type": "log", "line": "worker-log"})
    runner._sync_from_spool(_task(task_id))

    snap = _task(task_id).snapshot()
    assert snap["status"] == "running"
    assert snap["stage"] == "learning"
    assert snap["progress"] == pytest.approx(0.4)
    assert "worker-log" in list(_task(task_id).log_tail)

    on_done(
        task_id,
        JobResult(
            "succeeded",
            result_ref=task_id,
            metrics={"model_path": "/tmp/m.zip", "meta_path": "/tmp/m.zip.meta.json"},
        ),
    )
    done = _task(task_id).snapshot()
    assert done["status"] == "done"
    assert done["model_path"] == "/tmp/m.zip"
    assert task_id not in runner._pool_jobs
    assert not spool.snapshot_path(task_id).exists()


def test_pool_failure_maps_to_error_task(monkeypatch):
    fake = _FakePool()
    monkeypatch.setattr(runner, "pool_enabled", lambda: True)
    monkeypatch.setattr(runner, "_job_pool", lambda: fake)

    task_id = runner.submit_train_task({"algorithm": "ppo"})
    _, on_done = fake.submitted[0]
    on_done(task_id, JobResult("failed", result_ref=task_id, error="ValueError: boom"))

    snap = _task(task_id).snapshot()
    assert snap["status"] == "error"
    assert snap["error"] == "ValueError: boom"


def test_cancel_pool_job_writes_stop_flag(monkeypatch):
    fake = _FakePool()
    monkeypatch.setattr(runner, "pool_enabled", lambda: True)
    monkeypatch.setattr(runner, "_job_pool", lambda: fake)

    task_id = runner.submit_train_task({"algorithm": "ppo"})
    assert runner.cancel_task(task_id) is True

    assert spool.stop_requested(task_id)  # worker 侧据此在阶段边界退出
    assert _task(task_id).snapshot()["status"] == "cancelled"


def test_config_payload_rejects_preloaded_dataframe():
    pd = pytest.importorskip("pandas")
    from services.rl_service import RLTrainConfig

    assert runner._config_payload({"algorithm": "ppo"}) == {"algorithm": "ppo"}
    assert runner._config_payload("not-a-config") is None

    data = pd.DataFrame({"close": [1.0, 2.0]})
    assert runner._config_payload(RLTrainConfig(algorithm="ppo", data=data)) is None
    assert runner._config_payload({"algorithm": "ppo", "data": data}) is None


def test_config_payload_serializes_nested_cost_profile():
    from services.rl_service import RLTrainConfig

    config = RLTrainConfig(algorithm="ppo", cost_profile={"default": 0.0004})
    payload = runner._config_payload(config)
    assert payload is not None
    assert payload["cost_profile"]["default"] == pytest.approx(0.0004)
    # worker 侧按同一 payload 重建配置不应抛错
    rebuilt = RLTrainConfig(**payload)
    assert rebuilt.cost_profile.default == pytest.approx(0.0004)


def test_worker_runs_training_and_reports_through_spool(monkeypatch):
    seen: dict[str, object] = {}

    class FakeRLService:
        def train(self, config, reporter=None):
            seen["config"] = config
            reporter.state(stage="learning", progress=0.5, message="训练中")
            reporter.log("half")
            return SimpleNamespace(model_id="m1", model_path="/tmp/x.zip", metrics={})

    monkeypatch.setattr(rl_service_mod, "RLService", FakeRLService)
    spec = JobSpec(job_id="job-ok", kind="rl_train", payload={"config": {"algorithm": "ppo"}})
    result = rl_train_job.run_rl_train_job(spec)

    assert result.status == "succeeded"
    assert result.metrics["model_path"] == "/tmp/x.zip"
    assert result.metrics["meta_path"] == "/tmp/x.zip.meta.json"
    assert seen["config"].algorithm == "ppo"

    snap = spool.read_snapshot("job-ok")
    assert snap is not None
    assert snap["stage"] == "saving"
    assert snap["progress"] == 1.0
    events, _ = spool.read_events("job-ok", 0)
    assert any(e.get("line") == "half" for e in events)


def test_worker_maps_failure_to_failed_result(monkeypatch):
    class BoomService:
        def train(self, config, reporter=None):
            raise ValueError("bad hyperparams")

    monkeypatch.setattr(rl_service_mod, "RLService", BoomService)
    spec = JobSpec(job_id="job-boom", kind="rl_train", payload={"config": {"algorithm": "ppo"}})
    result = rl_train_job.run_rl_train_job(spec)

    assert result.status == "failed"
    assert result.error == "ValueError: bad hyperparams"


def test_worker_skips_training_when_cancelled_before_start(monkeypatch):
    spool.request_stop("job-stop")
    called: list[int] = []
    monkeypatch.setattr(rl_service_mod, "RLService", lambda: called.append(1))

    spec = JobSpec(job_id="job-stop", kind="rl_train", payload={"config": {"algorithm": "ppo"}})
    result = rl_train_job.run_rl_train_job(spec)

    assert result.status == "cancelled"
    assert called == []
