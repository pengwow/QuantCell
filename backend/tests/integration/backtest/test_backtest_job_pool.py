"""回测作业池并发 / 崩溃演练（M1 验收 Task 9）。

口径说明：回测 handler 在 worker 内走 `BacktestService`，数据源是本地 parquet 目录，
无法在子进程里注入假 provider；因此这里用池内自检作业（worker_entry 的 "sleep"）
度量池本身的并发度与进程数，回测业务正确性由 tests/unit/backtest 守护。
"""

import multiprocessing
import os
import signal
import threading
import time

import pytest

from jobs.pool import BoundedJobPool
from jobs.spec import JobResult, JobSpec

SLEEP_KIND = "sleep"


def _job(job_id: str, seconds: float) -> JobSpec:
    return JobSpec(job_id=job_id, kind=SLEEP_KIND, payload={"seconds": seconds})


def _wait_until(predicate, timeout: float, interval: float = 0.05) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def _worker_pids() -> list[int]:
    return [p.pid for p in multiprocessing.active_children() if p.pid]


@pytest.mark.timeout(120)  # xdist 下邻居争抢 CPU 拉长 spawn 冷启动，timeout=30 余量不足
def test_jobs_run_in_parallel_on_exactly_two_workers():
    """两个长作业的执行区间应重叠（真并行），且进程数恰为 2 并复用。"""
    pool = BoundedJobPool(max_workers=2, max_pending=8)
    try:
        # 用父进程单调时钟记完成时刻，配合子进程回传的 wall_seconds 反推开始时刻：
        # 两个区间相交即证明存在并行，且不受 spawn/torch 冷启动偏斜影响
        spans: dict[str, tuple[float, float, int]] = {}

        def on_done(job_id: str, result: JobResult) -> None:
            end = time.monotonic()
            wall = float(result.metrics["wall_seconds"])
            spans[job_id] = (end - wall, end, int(result.metrics["pid"]))

        for spec in [_job(f"par-{i}", 1.5) for i in range(2)]:
            pool.submit(spec, on_done)

        assert _wait_until(lambda: len(spans) == 2, 60, interval=0.02)
        (a_start, a_end, a_pid), (b_start, b_end, b_pid) = spans["par-0"], spans["par-1"]
        assert a_start < b_end and b_start < a_end, f"执行区间不相交（串行）: {spans}"
        assert a_pid != b_pid, f"两个作业应落在不同 worker: {spans}"

        # 复用性：再提 4 个短作业，不得新增进程
        short_done: list[int] = []

        def on_short(job_id: str, result: JobResult) -> None:
            assert result.status == "succeeded", result
            short_done.append(int(result.metrics["pid"]))

        for spec in [_job(f"reuse-{i}", 0.05) for i in range(4)]:
            pool.submit(spec, on_short)

        assert _wait_until(lambda: len(short_done) == 4, 60, interval=0.02)
        assert set(short_done) <= {a_pid, b_pid}, f"短作业未复用已有 worker: {short_done}"
        assert len(_worker_pids()) == 2
    finally:
        pool.shutdown(wait=True)


def test_sigkill_worker_marks_interrupted_and_pool_recovers():
    """kill -9 唯一 worker：在跑作业转 interrupted，池重建后可再次提作业。"""
    pool = BoundedJobPool(max_workers=1, max_pending=4)
    try:
        results: dict[str, JobResult] = {}
        killed = threading.Event()
        resubmitted = threading.Event()

        def on_done(job_id: str, result: JobResult) -> None:
            results[job_id] = result
            killed.set()

        pool.submit(_job("crash", 30.0), on_done)

        # 单 worker 池：running 时活跃子进程即是正在执行该作业的进程
        assert _wait_until(lambda: pool.status_counts()["running"] == 1 and _worker_pids(), 60)
        pid = _worker_pids()[0]
        os.kill(pid, signal.SIGKILL)

        assert killed.wait(30), "kill -9 后作业未收到 interrupted 结果"
        assert results["crash"].status == "interrupted", results["crash"]

        # 池已重建（generation 递增），重新投递应正常完成
        def on_resubmit(job_id: str, result: JobResult) -> None:
            results[job_id] = result
            resubmitted.set()

        pool.submit(_job("retry", 0.05), on_resubmit)
        assert resubmitted.wait(60), "崩溃恢复后重新提作业未完成"
        assert results["retry"].status == "succeeded", results["retry"]
    finally:
        pool.shutdown(wait=True)
