"""回测作业的 worker 侧适配层（进程池 handler）。

职责边界：
- 在 worker 进程内跑回测，**不写数据库**（DB 写入全部由 API 进程的
  BacktestJobManager 完成）
- 进度经 SpoolProgressTracker 限频写 JSON 快照文件，供 API 进程 relay 消费
- 取消由 stop 标志文件驱动（stop_control → progress_spool.CrossProcessStopEvent）
"""

from __future__ import annotations

import os
import time
from typing import Any

from backtest.async_runner import run_backtest_task
from backtest.progress_tracker import BacktestProgress, BacktestProgressTracker
from backtest.strategy_loader_service import StrategyLoaderService
from jobs import progress_spool
from jobs.spec import JobResult, JobSpec
from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)


class SpoolProgressTracker:
    """worker 侧进度代理：计算沿用 BacktestProgressTracker，输出改为文件快照。

    每次变更限频落盘（默认 1s），避免逐 bar 写文件把 IO 打满；终态强制落盘，
    保证 API 进程的 relay 能看到最后一次状态。
    """

    def __init__(self, job_id: str, interval: float = 1.0) -> None:
        self._job_id = job_id
        self._interval = interval
        self._inner = BacktestProgressTracker()
        self._last_flush = 0.0

    def create_progress(self, task_id: str) -> BacktestProgress:
        progress = self._inner.create_progress(task_id)
        self.flush(progress, force=True)
        return progress

    def update_progress(self, task_id: str, stage: str, data: dict[str, Any]) -> BacktestProgress | None:
        progress = self._inner.update_progress(task_id, stage, data)
        if progress is not None:
            self.flush(progress)
        return progress

    def complete_progress(self, task_id: str) -> BacktestProgress | None:
        progress = self._inner.complete_progress(task_id)
        if progress is not None:
            self.flush(progress, force=True)
        return progress

    def fail_progress(self, task_id: str, error_message: str, stage: str = "") -> BacktestProgress | None:
        progress = self._inner.fail_progress(task_id, error_message, stage)
        if progress is not None:
            self.flush(progress, force=True)
        return progress

    def flush_current(self, task_id: str) -> None:
        """强制把当前进度写盘（作业收尾兜底，防最后一次更新被限频吞掉）。"""
        progress = self._inner.get_progress(task_id)
        if progress is not None:
            self.flush(progress, force=True)

    def flush(self, progress: BacktestProgress, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_flush < self._interval:
            return
        self._last_flush = now
        progress_spool.write_snapshot(
            self._job_id,
            {"pid": os.getpid(), "ts": time.time(), "progress": progress.model_dump(mode="json")},
        )


def run_backtest_job(spec: JobSpec) -> JobResult:
    """进程池 handler：按 JobSpec 执行回测并返回 JobResult。"""
    task_id = spec.job_id
    payload = spec.payload
    strategy_name = str(payload.get("strategy_name") or "")
    backtest_config = payload.get("backtest_config") or {}

    # worker 内重新 import 策略：父进程只传名字，不做 pickle（策略模块不可序列化）
    if not strategy_name or StrategyLoaderService._find_strategy_file(strategy_name) is None:
        return JobResult(status="failed", error=f"策略文件不存在: {strategy_name}.py")

    tracker = SpoolProgressTracker(task_id)
    tracker.create_progress(task_id)
    progress_spool.bind_job(task_id)
    try:
        result = run_backtest_task(
            task_id,
            strategy_name,
            dict(payload.get("strategy_params") or {}),
            dict(backtest_config),
            tracker,
        )
    except Exception as exc:
        logger.exception(f"[作业 {task_id}] 回测执行异常")
        tracker.fail_progress(task_id, f"{type(exc).__name__}: {exc}", "execution")
        return JobResult(status="failed", error=f"{type(exc).__name__}: {exc}")
    finally:
        progress_spool.unbind_job()

    status = result.get("status")
    if status in ("success", "completed"):
        job_status = "succeeded"
    elif status == "stopped":
        job_status = "cancelled"
    else:
        job_status = "failed"

    tracker.flush_current(task_id)

    logger.info(f"[作业 {task_id}] 回测结束 status={status} job_status={job_status}")
    return JobResult(
        status=job_status,
        result_ref=task_id,
        error=None if job_status == "succeeded" else str(result.get("message") or ""),
        metrics={"symbols": len(backtest_config.get("symbols") or [])},
    )
