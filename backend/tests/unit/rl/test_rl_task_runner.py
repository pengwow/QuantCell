"""RL 训练任务化 runner 单测：排队 / 进度 / 取消 / 错误传播 / 事件流。

真实 SB3 训练全部 monkeypatch 掉（`train_fn` 注入），只验证 runner 的状态机。
"""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest

from services import rl_task_runner as runner


@pytest.fixture(autouse=True)
def _clean_registry():
    runner.reset_tasks()
    yield
    # 等上一个用例的工作线程把任务推进到终态，再清任务表（并发=1 的断言依赖空闲）
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if all(s["status"] in runner.TERMINAL_STATUSES for s in runner.list_tasks()):
            break
        time.sleep(0.01)
    runner.reset_tasks()


def _wait(predicate, timeout: float = 5.0, interval: float = 0.01):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(interval)
    raise AssertionError("等待超时")


def _snapshot(task_id: str) -> dict:
    task = runner.get_task(task_id)
    assert task is not None
    return task.snapshot()


def _wait_status(task_id: str, status: str, timeout: float = 5.0) -> dict:
    return _wait(lambda: (snap := _snapshot(task_id))["status"] == status and snap, timeout=timeout)


def test_submit_runs_reports_progress_and_lands_done():
    gate = threading.Event()

    def fake_train(config, reporter):
        assert config == "config-sentinel"
        reporter.state(stage="learning", progress=0.25, message="训练中")
        reporter.log("half way")
        gate.wait(5)
        reporter.state(stage="saving", progress=0.95, message="保存模型")
        return SimpleNamespace(model_id="m1", model_path="/tmp/models/m1.zip", metrics={})

    task_id = runner.submit_train_task("config-sentinel", train_fn=fake_train)
    # 提交即返回 queued（线程可能刚起步，也允许已是 running）
    assert _snapshot(task_id)["status"] in {"queued", "running"}

    running = _wait(lambda: (s := _snapshot(task_id))["stage"] == "learning" and s)
    assert running["status"] == "running"
    assert running["progress"] == pytest.approx(0.25)
    assert running["message"] == "训练中"

    gate.set()
    done = _wait_status(task_id, "done")
    assert done["progress"] == 1.0
    assert done["model_path"] == "/tmp/models/m1.zip"
    assert done["meta_path"] == "/tmp/models/m1.zip.meta.json"
    assert done["error"] is None
    assert done["elapsed_ms"] >= 0
    assert set(done) == {
        "task_id",
        "status",
        "stage",
        "progress",
        "message",
        "error",
        "model_path",
        "meta_path",
        "elapsed_ms",
    }


def test_error_is_propagated_to_task():
    def boom(config, reporter):
        reporter.state(stage="learning", progress=0.1)
        raise ValueError("bad hyperparams")

    task_id = runner.submit_train_task(None, train_fn=boom)
    failed = _wait_status(task_id, "error")
    assert failed["error"] == "ValueError: bad hyperparams"
    assert failed["message"] == "训练失败"


def test_cancel_stops_running_task_at_checkpoint():
    started = threading.Event()

    def long_train(config, reporter):
        started.set()
        for _ in range(500):
            reporter.check_cancel()  # 阶段边界检查
            reporter.state(stage="learning", progress=0.5)
            time.sleep(0.005)
        return SimpleNamespace(model_id="never", model_path=None, metrics={})

    task_id = runner.submit_train_task(None, train_fn=long_train)
    assert started.wait(5)

    assert runner.cancel_task(task_id) is True
    cancelled = _wait_status(task_id, "cancelled")
    assert cancelled["message"] == "训练已取消"


def test_cancel_queued_task_skips_training():
    gate = threading.Event()
    calls: list[str] = []

    def blocking(config, reporter):
        calls.append("first")
        gate.wait(5)
        return SimpleNamespace(model_id="m1", model_path=None, metrics={})

    runner.submit_train_task(None, train_fn=blocking)
    _wait(lambda: calls == ["first"])

    second = runner.submit_train_task(None, train_fn=lambda c, r: calls.append("second"))
    assert _snapshot(second)["status"] == "queued"  # 并发=1：排队

    assert runner.cancel_task(second) is True
    snap = _snapshot(second)
    assert snap["status"] == "cancelled"
    assert "未开始" in snap["message"]

    gate.set()
    time.sleep(0.1)
    assert calls == ["first"]  # 排队任务被取消后不会真的开跑


def test_concurrency_quota_runs_two_tasks_in_parallel(monkeypatch):
    """配额=2：两个任务同时开跑（旧的全局互斥锁下第二个会一直排队）。"""
    gate = threading.Event()
    started: list[str] = []

    def blocking(config, reporter):
        started.append(config)
        gate.wait(5)
        return SimpleNamespace(model_id="m", model_path=None, metrics={})

    monkeypatch.setattr(runner, "_concurrency_limit", lambda: 2)
    first = runner.submit_train_task("a", train_fn=blocking)
    second = runner.submit_train_task("b", train_fn=blocking)

    _wait(lambda: len(started) == 2)
    assert {t["status"] for t in runner.list_tasks()} == {"running"}

    gate.set()
    assert _wait_status(first, "done")["status"] == "done"
    assert _wait_status(second, "done")["status"] == "done"


def test_cancel_terminal_task_returns_false():
    task_id = runner.submit_train_task(None, train_fn=lambda c, r: SimpleNamespace(model_id="x", model_path=None))
    _wait_status(task_id, "done")
    assert runner.cancel_task(task_id) is False


def test_cancel_unknown_task_raises_keyerror():
    with pytest.raises(KeyError):
        runner.cancel_task("rltrain_missing")


def test_sse_stream_states_logs_and_terminal_close():
    gate = threading.Event()

    def fake_train(config, reporter):
        reporter.state(stage="learning", progress=0.3, message="训练中")
        reporter.log("line-1")
        gate.wait(5)
        return SimpleNamespace(model_id="m1", model_path=None, metrics={})

    task_id = runner.submit_train_task(None, train_fn=fake_train)
    task = runner.get_task(task_id)
    assert task is not None
    _wait(lambda: _snapshot(task_id)["stage"] == "learning")

    frames: list[str] = []
    threading.Timer(0.2, gate.set).start()
    for frame in runner.sse_stream(task):
        frames.append(frame)

    states = [f for f in frames if f.startswith("event: state")]
    logs = [f for f in frames if f.startswith("event: log")]
    assert logs and any("line-1" in frame for frame in logs)
    assert states and '"status": "done"' in states[-1]  # 终态推 state 后关闭
    assert "训练中" in states[0]


def test_sse_stream_of_finished_task_closes_immediately():
    task_id = runner.submit_train_task(None, train_fn=lambda c, r: SimpleNamespace(model_id="x", model_path=None))
    _wait_status(task_id, "done")
    task = runner.get_task(task_id)
    assert task is not None

    frames = list(runner.sse_stream(task))
    assert frames[0].startswith("event: state")
    assert '"status": "done"' in frames[0]


def test_scaled_reporter_maps_progress_into_parent_window():
    class Recorder(runner.NullReporter):
        active = True

        def __init__(self):
            self.seen: list[tuple[str | None, float | None]] = []

        def state(self, *, stage=None, progress=None, message=""):
            self.seen.append((stage, progress))

    inner = Recorder()
    scaled = runner.ScaledReporter(inner, base=0.5, span=0.5)
    scaled.state(stage="learning", progress=0.4)
    assert inner.seen == [("learning", pytest.approx(0.7))]


def test_learn_in_chunks_cancels_between_chunks():
    """分块 learn：取消在块间生效（不做真实 SB3 训练）。"""

    class FakeModel:
        def __init__(self):
            self.calls = 0

        def learn(self, *, total_timesteps, reset_num_timesteps=False, callback=None):
            self.calls += 1

    reporter = runner.TrainTask(task_id="t")
    reporter.active = True
    model = FakeModel()

    def cancel_after_first_chunk():
        if model.calls >= 2:
            reporter.cancel_event.set()

    original_learn = model.learn

    def learn_with_cancel(**kwargs):
        original_learn(**kwargs)
        cancel_after_first_chunk()

    model.learn = learn_with_cancel

    with pytest.raises(runner.TrainingCancelled):
        runner.learn_in_chunks(model, 8_000, reporter, stage="learning")

    assert model.calls == 2  # 第三块开始前被取消拦下
    assert reporter.snapshot()["progress"] > 0


@pytest.mark.slow
def test_real_ppo_training_reports_through_reporter(tmp_path, monkeypatch):
    """真实 SB3 + axon_quant 短训练：reporter 收到阶段/日志且最终 progress=1.0。

    `total_timesteps=64` 落在单块区间（< `_MIN_CHUNK_STEPS`），验证的是 reporter
    接线与回调链路，不是分块本身（分块由上面的假模型用例覆盖）。
    """
    pytest.importorskip("stable_baselines3", reason="stable_baselines3 未安装")
    import pandas as pd

    import services.rl_service as rl_service_mod
    from services.rl_service import RLTrainConfig

    monkeypatch.setattr(rl_service_mod, "MODELS_DIR", tmp_path)
    rows = 48
    data = pd.DataFrame(
        {
            "timestamp": range(1_700_000_000, 1_700_000_000 + rows * 3_600, 3_600),
            "open": [100.0 + i * 0.1 for i in range(rows)],
            "high": [101.0 + i * 0.1 for i in range(rows)],
            "low": [99.0 + i * 0.1 for i in range(rows)],
            "close": [100.5 + i * 0.1 for i in range(rows)],
            "volume": [1_000.0] * rows,
        }
    )
    task = runner.TrainTask(task_id="real-ppo")

    result = rl_service_mod.RLService().train(
        RLTrainConfig(algorithm="ppo", data=data, total_timesteps=64, model_name="reporter_smoke"),
        reporter=task,
    )

    snap = task.snapshot()
    assert snap["progress"] == 1.0
    assert snap["stage"] in {"learning", "saving", "loading_data"}  # 终态由 runner 落，训练侧只报过程
    assert any("训练" in line for line in task.log_tail)
    assert result.model_path is not None and result.model_path.endswith(".zip")
