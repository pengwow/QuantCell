"""有界进程池：并发上限、排队上限、worker 崩溃后的恢复能力。"""

import queue
import time
from types import SimpleNamespace

import pytest

import jobs.pool as pool_module
from jobs.pool import BoundedJobPool, JobPoolFullError, parse_core_range
from jobs.spec import JobSpec


def _put_result(events: queue.Queue):
    def _callback(job_id: str, result) -> None:
        events.put((job_id, result))

    return _callback


def _wait(events: queue.Queue, expected: int, timeout: float = 120.0) -> dict:
    results = {}
    deadline = time.monotonic() + timeout
    while len(results) < expected:
        remaining = deadline - time.monotonic()
        assert remaining > 0, f"等待作业回调超时，已收到 {len(results)}/{expected}"
        job_id, result = events.get(timeout=remaining)
        results[job_id] = result
    return results


def _wait_until(predicate, timeout: float = 120.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, "等待池状态超时"
        time.sleep(0.05)


def test_parse_core_range():
    assert parse_core_range("4-6") == [4, 5, 6]
    assert parse_core_range("4,6 8") == [4, 6, 8]
    assert parse_core_range("") == []
    with pytest.raises(ValueError, match="绑核区间非法"):
        parse_core_range("6-4")


def test_pool_bounds_workers_and_rejects_overflow():
    events: queue.Queue = queue.Queue()
    pool = BoundedJobPool(max_workers=2, max_pending=1)
    try:
        started = time.monotonic()
        # max_pending=1 时"排队中"也算占坑，逐个提交并等调度线程取走，避免把上限语义测成竞态
        for index in (0, 1):
            pool.submit(
                JobSpec(job_id=f"sleep-{index}", kind="sleep", payload={"seconds": 0.4}),
                _put_result(events),
            )
            _wait_until(lambda: pool.status_counts()["running"] == index + 1)

        # 2 个在跑 + 1 个排队 = 占满 max_pending，下一个必须当场拒收而不是阻塞
        pool.submit(JobSpec(job_id="sleep-2", kind="sleep", payload={"seconds": 0.4}), _put_result(events))
        _wait_until(lambda: pool.status_counts()["queued"] == 1)
        with pytest.raises(JobPoolFullError):
            pool.submit(JobSpec(job_id="overflow", kind="sleep"))

        _wait_until(lambda: pool.status_counts()["queued"] == 0)
        pool.submit(JobSpec(job_id="sleep-3", kind="sleep", payload={"seconds": 0.4}), _put_result(events))

        results = _wait(events, 4)
        elapsed = time.monotonic() - started
    finally:
        pool.shutdown()

    assert all(result.status == "succeeded" for result in results.values())
    # 进程复用且不超上限：pids 数量 ≤ 2
    assert len({result.metrics["pid"] for result in results.values()}) <= 2
    # 4 个 0.4s 作业在 2 并发下至少跑两批
    assert elapsed >= 0.7


def test_job_lifecycle_logs_share_job_id(monkeypatch):
    """全链路日志可按 job_id 串联：enqueue → start → finish 三阶段。"""

    class _Recorder:
        def __init__(self) -> None:
            self.messages: list[str] = []

        def info(self, message: str) -> None:
            self.messages.append(message)

        def error(self, message: str) -> None:
            self.messages.append(message)

    recorder = _Recorder()
    monkeypatch.setattr(pool_module, "logger", recorder)

    events: queue.Queue = queue.Queue()
    pool = BoundedJobPool(max_workers=1)
    try:
        pool.submit(JobSpec(job_id="log-job", kind="sleep", payload={"seconds": 0.01}), _put_result(events))
        _wait(events, 1)
    finally:
        pool.shutdown()

    joined = "\n".join(recorder.messages)
    for event in ("event=enqueue", "event=start", "event=finish"):
        assert f"job_id=log-job {event}" in joined


def test_pool_enabled_tri_state(monkeypatch):
    """显式 false 必须能覆盖 config.toml 的 true（三态开关，None 才回落配置）。"""
    monkeypatch.setattr(pool_module, "get_flag", lambda key, default: True)
    monkeypatch.setattr(pool_module, "get_settings", lambda: SimpleNamespace(job_pool_enabled=False))
    assert pool_module.pool_enabled() is False
    monkeypatch.setattr(pool_module, "get_settings", lambda: SimpleNamespace(job_pool_enabled=True))
    assert pool_module.pool_enabled() is True

    monkeypatch.setattr(pool_module, "get_settings", lambda: SimpleNamespace(job_pool_enabled=None))
    assert pool_module.pool_enabled() is True
    monkeypatch.setattr(pool_module, "get_flag", lambda key, default: False)
    assert pool_module.pool_enabled() is False


def test_pool_resources_split_cores_between_pools(monkeypatch):
    """回测与 HPO 池不能共用同一批核（否则 2N 个 worker 绑到 N 个核上互抢）。"""
    monkeypatch.setattr(pool_module, "resolve_cores", lambda: [4, 5, 6, 7])
    assert pool_module.pool_resources("backtest") == (2, [4, 5])
    assert pool_module.pool_resources("hpo") == (2, [6, 7])

    # 单核区间只能共享，两池各 1 并发
    monkeypatch.setattr(pool_module, "resolve_cores", lambda: [4])
    assert pool_module.pool_resources("backtest") == (1, [4])
    assert pool_module.pool_resources("hpo") == (1, [4])

    # 未绑核：保持默认并发，不做静态切分
    monkeypatch.setattr(pool_module, "resolve_cores", lambda: [])
    workers, cores = pool_module.pool_resources("backtest")
    assert cores == []
    assert workers == pool_module.default_max_workers([])


def test_cancel_queued_removes_job_without_running():
    events: queue.Queue = queue.Queue()
    pool = BoundedJobPool(max_workers=1, max_pending=4)
    try:
        pool.submit(JobSpec(job_id="blocker", kind="sleep", payload={"seconds": 0.5}), _put_result(events))
        _wait_until(lambda: pool.status_counts()["running"] == 1)
        pool.submit(JobSpec(job_id="queued", kind="sleep", payload={"seconds": 0.01}), _put_result(events))
        _wait_until(lambda: pool.status_counts()["queued"] == 1)

        assert pool.cancel_queued("queued") is True
        assert pool.cancel_queued("missing") is False

        results = _wait(events, 2)
    finally:
        pool.shutdown()

    assert results["blocker"].status == "succeeded"
    assert results["queued"].status == "interrupted"


def test_terminal_states_are_cleared_but_counted():
    events: queue.Queue = queue.Queue()
    pool = BoundedJobPool(max_workers=1)
    try:
        pool.submit(JobSpec(job_id="done-job", kind="sleep", payload={"seconds": 0.01}), _put_result(events))
        _wait(events, 1)
        _wait_until(lambda: pool.status_counts()["succeeded"] == 1)
        # 终态不再滞留 _states（长跑进程内存不随作业数增长），但计数仍可观测
        assert pool._states == {}
        assert pool.status_counts()["succeeded"] == 1
    finally:
        pool.shutdown()


def test_shutdown_without_wait_terminates_busy_workers():
    """应用退出路径：wait=False 必须杀掉在跑 worker，不能留孤儿进程。"""
    pool = BoundedJobPool(max_workers=1)
    pool.submit(JobSpec(job_id="long", kind="sleep", payload={"seconds": 30}), None)
    # running 状态先于 executor.submit 返回，必须等进程对象也创建出来再取列表
    _wait_until(lambda: pool.status_counts()["running"] == 1 and bool(pool._executor._processes))
    processes = list(pool._executor._processes.values())
    assert processes, "worker 应已启动"

    pool.shutdown(wait=False)

    for process in processes:
        process.join(timeout=5)
        assert not process.is_alive(), "wait=False 关闭后 worker 仍在运行（孤儿进程）"


def test_pool_recovers_after_worker_crash():
    events: queue.Queue = queue.Queue()
    pool = BoundedJobPool(max_workers=1, max_pending=2)
    try:
        # payload.die 让 worker 直接 os._exit(1)，等价于 kill -9
        pool.submit(JobSpec(job_id="crash", kind="sleep", payload={"die": True}), _put_result(events))
        crashed = _wait(events, 1)
        assert crashed["crash"].status == "interrupted"

        # 池已重建，可继续接单
        pool.submit(JobSpec(job_id="after-crash", kind="sleep", payload={"seconds": 0.01}), _put_result(events))
        recovered = _wait(events, 1)
    finally:
        pool.shutdown()

    assert recovered["after-crash"].status == "succeeded"
