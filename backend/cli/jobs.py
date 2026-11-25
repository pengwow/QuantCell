"""作业池 CLI：不起 API 服务，直接用命令行验证多进程作业池。

用法：
    uv run python -m cli jobs config      # 观测配置：灰度开关 / 绑核 / 两池并发
    uv run python -m cli jobs selftest    # 一键自检：并行 / 拒收 / 撤销 / 终态清理 / 退出杀 worker

自检用 worker_entry 内置的 "sleep" 空转作业，不依赖行情数据，
内容与 tests/integration/backtest/test_backtest_job_pool.py 同口径。
"""

import multiprocessing
import threading
import time
from collections.abc import Callable
from typing import Any

import typer

from cli._common import handle_errors
from jobs.pool import (
    BoundedJobPool,
    JobPoolFullError,
    pool_enabled,
    pool_resources,
    resolve_cores,
)
from jobs.spec import JobSpec
from utils.logger import LogType, get_logger

app = typer.Typer(name="jobs", help="作业池观测与自检", add_completion=False)
logger = get_logger(__name__, LogType.APPLICATION)

# 记录自检项结果的回调：(名称, 是否通过, 补充信息)
Record = Callable[[str, bool, str], None]


def _wait_until(predicate: Callable[[], bool], timeout: float, interval: float = 0.05) -> bool:
    """轮询等待条件成立，超时返回 False（CLI 演练用小工具，与集成测试同款）。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def _sleep_spec(job_id: str, seconds: float) -> JobSpec:
    return JobSpec(job_id=job_id, kind="sleep", payload={"seconds": seconds})


def _active_worker_pids() -> list[int]:
    """当前还活着的池 worker 进程（active_children 会顺带回收已退出的）。"""
    return [p.pid for p in multiprocessing.active_children() if p.pid]


@app.command("config")
@handle_errors
def show_config() -> None:
    """查看作业池配置（只读，不创建进程池）。"""
    bt_workers, bt_cores = pool_resources("backtest")
    hpo_workers, hpo_cores = pool_resources("hpo")
    typer.echo(f"灰度开关 pool_enabled : {pool_enabled()}")
    typer.echo(f"绑核区间 resolve_cores: {resolve_cores() or '（未绑定，交 OS 调度）'}")
    typer.echo(f"回测池 并发/绑核      : {bt_workers} / {bt_cores or '-'}")
    typer.echo(f"HPO 池 并发/绑核      : {hpo_workers} / {hpo_cores or '-'}")


def _check_parallel(record: Record) -> None:
    """检查 1：真并行 + worker 复用 + 终态计数。"""
    pool = BoundedJobPool(max_workers=2, max_pending=8)
    try:
        spans: dict[str, tuple[float, float, int]] = {}
        both_done = threading.Event()

        def on_first(job_id: str, result: Any) -> None:
            end = time.monotonic()
            # 用结束时刻减回传的 wall_seconds 反推开始区间，区间相交即证明真并行
            spans[job_id] = (end - float(result.metrics["wall_seconds"]), end, int(result.metrics["pid"]))
            if len(spans) == 2:
                both_done.set()

        for i in range(2):
            pool.submit(_sleep_spec(f"par-{i}", 1.0), on_first)

        if not both_done.wait(60):
            record("两个作业真并行（区间相交且不同 worker）", False, "60s 内未全部完成")
            return
        (a0, a1, _), (b0, b1, _) = spans["par-0"], spans["par-1"]
        record(
            "两个作业真并行（区间相交且不同 worker）",
            a0 < b1 and b0 < a1 and len({pid for *_, pid in spans.values()}) == 2,
            f"spans={spans}",
        )

        short_pids: list[int] = []

        def on_short(job_id: str, result: Any) -> None:
            short_pids.append(int(result.metrics["pid"]))

        for i in range(4):
            pool.submit(_sleep_spec(f"reuse-{i}", 0.05), on_short)
        ok = _wait_until(lambda: len(short_pids) == 4, 60)
        record(
            "后续短作业复用既有 worker（不增进程）",
            ok and set(short_pids) <= {pid for *_, pid in spans.values()},
            f"pids={sorted(set(short_pids))}",
        )

        counts = pool.status_counts()
        record("终态作业被清理且计数保留（succeeded=6）", counts.get("succeeded") == 6, str(counts))
    finally:
        pool.shutdown(wait=True)


def _check_reject_and_cancel(record: Record) -> None:
    """检查 2：排队上限拒收 + 取消排队作业 + 运行中作业不受影响。"""
    pool = BoundedJobPool(max_workers=1, max_pending=1)
    try:
        statuses: dict[str, str] = {}

        def on_done(job_id: str, result: Any) -> None:
            statuses[job_id] = result.status

        pool.submit(_sleep_spec("busy", 3.0), on_done)  # 占住唯一 worker
        ok = _wait_until(lambda: pool.status_counts().get("running") == 1, 30)
        record("作业占住唯一 worker 进入 running", ok)
        if not ok:
            return

        pool.submit(_sleep_spec("queued-1", 0.05), on_done)  # 占满唯一排队位
        rejected = False
        try:
            pool.submit(_sleep_spec("queued-2", 0.05), on_done)
        except JobPoolFullError:
            rejected = True
        record("排队已满抛 JobPoolFullError", rejected)

        record("cancel_queued 撤销排队作业返回 True", pool.cancel_queued("queued-1") is True)
        record("cancel_queued 未知 job_id 返回 False", pool.cancel_queued("no-such-job") is False)

        ok = _wait_until(lambda: statuses.get("busy") == "succeeded", 30)
        record("运行中作业不受撤销影响并正常完成", ok, f"busy={statuses.get('busy')}")
    finally:
        pool.shutdown(wait=True)


def _check_shutdown(record: Record) -> None:
    """检查 3：wait=False 关闭时不留孤儿 worker 进程。"""
    pool = BoundedJobPool(max_workers=1, max_pending=2)
    try:
        pool.submit(_sleep_spec("long", 30.0), lambda j, r: None)
        ok = _wait_until(lambda: pool.status_counts().get("running") == 1 and bool(_active_worker_pids()), 60)
        if not ok:
            record("wait=False 关闭后 worker 进程全部退出", False, "作业未进入 running")
            return
        pids_before = _active_worker_pids()
        pool.shutdown(wait=False)
        record(
            "wait=False 关闭后 worker 进程全部退出",
            _wait_until(lambda: not _active_worker_pids(), 15),
            f"关闭前 pids={pids_before}",
        )
    finally:
        # shutdown 可重入：上面已 wait=False 关闭过则此处为收尾无操作
        pool.shutdown(wait=False)


@app.command("selftest")
@handle_errors
def selftest() -> None:
    """一键自检作业池核心行为（真 spawn 子进程，约 10~20 秒，全部通过退出码为 0）。"""
    checks: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))
        typer.echo(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
        logger.info(f"作业池自检 event={'pass' if ok else 'fail'} item={name}")

    logger.info("作业池 CLI 自检开始")
    _check_parallel(record)
    _check_reject_and_cancel(record)
    _check_shutdown(record)

    failed = [name for name, ok, _ in checks if not ok]
    if failed:
        logger.error(f"作业池 CLI 自检失败: {failed}")
        typer.echo(f"自检失败 {len(failed)}/{len(checks)} 项", err=True)
        raise typer.Exit(1)
    logger.info(f"作业池 CLI 自检通过: {len(checks)} 项")
    typer.echo(f"自检通过（{len(checks)}/{len(checks)}）")
