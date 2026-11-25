"""回测作业调度层（API 进程侧）。

把回测投递到 BoundedJobPool，并承担所有父进程职责：
- 消费 worker 写在文件里的进度快照 → 更新内存 tracker + 限频落库
- 终态统一落库（async_task_records + backtest_tasks）与通知
- stop：写取消标志文件 + 限时等待，超时按快照里的 pid 强杀

worker 只跑计算、不碰数据库；这里才是 DB 写入的唯一入口。
"""

from __future__ import annotations

import os
import signal
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select

from backtest.progress_tracker import BacktestProgress, get_progress_tracker
from backtest.service import BacktestService
from common.notifications.task_notices import (
    TASK_STATUS_INTERRUPTED,
    notify_task_event,
    upsert_async_task_record,
)
from jobs import progress_spool
from jobs.pool import BoundedJobPool, pool_resources
from jobs.spec import JobResult, JobSpec
from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)

# 心跳：超过该时长没有新快照就判定 worker 僵死/被杀（M1 Task 8 的 75s 口径）
HEARTBEAT_TIMEOUT_SECONDS = 75.0
RELAY_INTERVAL_SECONDS = 1.0
DB_FLUSH_INTERVAL_SECONDS = 2.0


@dataclass
class _JobState:
    """父进程侧的单作业状态（不投递、不进池）。"""

    strategy_name: str | None
    done: threading.Event = field(default_factory=threading.Event)
    pid: int | None = None
    last_seen: float = field(default_factory=time.time)
    finalized: bool = False
    last_db_flush: float = 0.0


class BacktestJobManager:
    """回测作业池管理器（进程内单例，见模块底部 backtest_job_manager）。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pool: BoundedJobPool | None = None
        self._jobs: dict[str, _JobState] = {}
        self._relay: threading.Thread | None = None
        self._relay_stop = threading.Event()
        self._service = BacktestService()

    # ------------------------------------------------------------------ 投递

    def submit(
        self,
        task_id: str,
        strategy_name: str,
        strategy_params: dict,
        backtest_config: dict,
    ) -> None:
        """投递回测作业；排队已满抛 JobPoolFullError（调用方决定 HTTP 语义）。"""
        spec = JobSpec(
            job_id=task_id,
            kind="backtest",
            payload={
                "strategy_name": strategy_name,
                "strategy_params": dict(strategy_params or {}),
                "backtest_config": dict(backtest_config or {}),
            },
        )
        pool = self._ensure_pool()
        with self._lock:
            self._jobs[task_id] = _JobState(strategy_name=strategy_name)
        try:
            pool.submit(spec, on_done=self._on_done)
        except Exception:
            with self._lock:
                self._jobs.pop(task_id, None)
            raise

        self._mark_db(task_id, "queued", strategy_name)
        self._ensure_relay()
        logger.info(f"[回测作业 {task_id}] 已投递进程池 strategy={strategy_name}")

    def pool_status(self) -> dict[str, int | list[int]] | None:
        """只读池状态；尚未创建时返回 None（观测接口不应因查询而建池）。"""
        with self._lock:
            pool = self._pool
        return pool.status_counts() if pool is not None else None

    def mark_rejected(self, task_id: str, name: str | None, error: str) -> None:
        """入池被拒（池满/重复 id）后的收尾：落 failed、发失败通知。"""
        tracker = get_progress_tracker()
        tracker.fail_progress(task_id, error, "data_prep")
        self._update_db_row(task_id, "failed")
        self._mark_db(task_id, "failed", name, error=error)
        self._notify(task_id, "failed", name, error)

    def _ensure_pool(self) -> BoundedJobPool:
        with self._lock:
            if self._pool is None:
                max_workers, cores = pool_resources("backtest")
                self._pool = BoundedJobPool(max_workers=max_workers, cores=cores)
                logger.info(f"回测进程池已创建 max_workers={self._pool.max_workers} cores={cores}")
            return self._pool

    def _ensure_relay(self) -> None:
        with self._lock:
            if self._relay is not None:
                return
            self._relay = threading.Thread(target=self._relay_loop, name="backtest-job-relay", daemon=True)
            self._relay.start()

    def shutdown(self) -> None:
        """应用退出时调用：停 relay、关池（wait=False 会 terminate 在跑 worker）。

        不关池的话 spawn worker 是独立子进程，API 退出（含 lifespan 的 os._exit）
        不会带走它们，重启后旧 worker 继续跑长回测并与新池争抢 CPU/绑核。
        """
        self._relay_stop.set()
        with self._lock:
            pool = self._pool
            self._pool = None
            self._relay = None
        if pool is not None:
            pool.shutdown(wait=False)

    # ------------------------------------------------------------------ 停止

    def stop(self, task_id: str, confirm_timeout: float = 8.0) -> dict | None:
        """终止进程池作业；不是本管理器投递的任务返回 None（调用方走线程路径）。"""
        with self._lock:
            state = self._jobs.get(task_id)
        if state is None:
            return None

        result = self._service.request_stop(task_id)
        if result.get("status") == "error":
            return result

        progress_spool.request_stop(task_id)
        if state.done.wait(confirm_timeout):
            return {"status": "success", "message": "回测已终止"}

        # 超时强杀：只杀该作业所在 worker 进程。
        # ponytail: 强杀会让整个进程池进入 BrokenProcessPool 恢复流程，同池其它在跑作业
        # 会被标 interrupted；当前只有回测共用此池，升级路径是按作业单独建池或做进程级隔离。
        with self._lock:
            # 已按用户意图收尾（task 文件 stopped），后续 on_done 的 interrupted 不再回写覆盖
            state.finalized = True
        snapshot = progress_spool.read_snapshot(task_id) or {}
        pid = snapshot.get("pid")
        if isinstance(pid, int) and pid > 0:
            try:
                os.kill(pid, signal.SIGKILL)
                logger.warning(f"[回测作业 {task_id}] 等待终止超时，已强杀 worker pid={pid}")
            except OSError as exc:
                logger.error(f"[回测作业 {task_id}] 强杀 worker 失败 pid={pid}: {exc}")
        return {"status": "forced", "message": "回测终止等待超时，已强制结束回测进程"}

    # ------------------------------------------------------------------ 进度

    def load_progress(self, task_id: str) -> BacktestProgress | None:
        """从影子表 extra.progress 还原进度（服务重启后内存快照丢失时的兜底）。"""
        # 函数内 import 原因：inbox_models 顶层导入会拉起 collector 包初始化，
        # 与 common.notifications 形成包级循环（同 task_notices 的处理方式）
        from common.notifications.inbox_models import AsyncTaskRecord

        try:
            from utils.db_session import use_db_session

            with use_db_session() as db:
                row = (
                    db.execute(
                        select(AsyncTaskRecord).where(
                            AsyncTaskRecord.task_type == "backtest",
                            AsyncTaskRecord.task_id == task_id,
                        )
                    )
                    .scalars()
                    .one_or_none()
                )
            payload = (row.extra or {}).get("progress") if row is not None else None
            if not isinstance(payload, dict):
                return None
            return BacktestProgress.model_validate(payload)
        except Exception as exc:
            logger.warning(f"[回测作业 {task_id}] 从影子表还原进度失败: {exc}")
            return None

    def _relay_loop(self) -> None:
        tracker = get_progress_tracker()
        while not self._relay_stop.wait(RELAY_INTERVAL_SECONDS):
            with self._lock:
                jobs = list(self._jobs.items())
            now = time.time()
            for job_id, state in jobs:
                if state.finalized:
                    continue
                snapshot = progress_spool.read_snapshot(job_id)
                if snapshot and isinstance(snapshot.get("progress"), dict):
                    if not state.finalized:
                        state.pid = snapshot.get("pid") or state.pid
                        state.last_seen = float(snapshot.get("ts") or now)
                    if tracker.apply_snapshot(job_id, snapshot["progress"]) is not None:
                        if now - state.last_db_flush >= DB_FLUSH_INTERVAL_SECONDS:
                            state.last_db_flush = now
                            self._mark_db(
                                job_id,
                                "running",
                                state.strategy_name,
                                progress=snapshot["progress"],
                            )
                # 心跳判定必须独立于快照是否存在：worker 卡死时快照文件仍留在磁盘上
                # （只在终态才 clear），若判定挂在 snapshot 的 elif 分支上就永远进不来。
                # 只在 worker 已真正开工（写过快照、有 pid）后才判定：
                # 排队等待中的作业没有快照属于正常，不能被误判成僵死。
                if state.pid is not None and now - state.last_seen > HEARTBEAT_TIMEOUT_SECONDS:
                    self._mark_heartbeat_timeout(job_id, state)

    # ------------------------------------------------------------------ 终态

    def _on_done(self, job_id: str, result: JobResult) -> None:
        with self._lock:
            state = self._jobs.pop(job_id, None)
            already_finalized = state.finalized if state is not None else False
        name = state.strategy_name if state is not None else None
        if state is not None:
            state.done.set()

        try:
            if not already_finalized:
                self._finalize(job_id, result, name)
        finally:
            progress_spool.clear(job_id)

    def _finalize(self, job_id: str, result: JobResult, name: str | None) -> None:
        tracker = get_progress_tracker()
        if result.status == "succeeded":
            tracker.complete_progress(job_id)
            self._update_db_row(job_id, "completed")
            self._mark_db(job_id, "succeeded", name)
            self._notify(job_id, "completed", name)
        elif result.status == "cancelled":
            # 用户终止：把 relay 可能覆盖成 completed 的进度改回 stopped
            tracker.update_progress(job_id, "overall", {"status": "stopped"})
            self._update_db_row(job_id, "stopped")
            self._mark_db(job_id, "cancelled", name)
            self._notify(job_id, "stopped", name)
        else:
            error = result.error or "回测执行失败"
            tracker.fail_progress(job_id, error, "execution")
            self._update_db_row(job_id, "failed")
            self._mark_db(job_id, result.status, name, error=error)
            if result.status == "interrupted":
                # 池恢复/进程被杀不是「回测逻辑失败」，通知语义要区分开
                notify_task_event("backtest", job_id, TASK_STATUS_INTERRUPTED, name=name, error=error)
            else:
                self._notify(job_id, "failed", name, error)

    def _mark_heartbeat_timeout(self, job_id: str, state: _JobState) -> None:
        with self._lock:
            if state.finalized:
                return
            state.finalized = True
        error = f"回测进程超过 {int(HEARTBEAT_TIMEOUT_SECONDS)} 秒无进度更新，判定为中断"
        logger.error(f"[回测作业 {job_id}] {error}")
        get_progress_tracker().fail_progress(job_id, error, "execution")
        self._update_db_row(job_id, "failed")
        self._mark_db(job_id, "interrupted", state.strategy_name, error=error)
        notify_task_event("backtest", job_id, TASK_STATUS_INTERRUPTED, name=state.strategy_name, error=error)
        # 尽力让僵死的 worker 在下一个协作点退出；不强杀（避免波及其它在跑作业）
        progress_spool.request_stop(job_id)

    def _notify(self, task_id: str, status: str, name: str | None, error: str | None = None) -> None:
        # 函数内 import 原因：notify_backtest_result 定义在 routes 里，而 routes 顶层
        # 导入本模块，顶层引用会形成循环；通知语义仍复用 routes 的唯一出口
        from backtest.routes import notify_backtest_result

        notify_backtest_result(task_id, {"status": status, "message": error}, name=name or "")

    # ------------------------------------------------------------------ 落库

    def _mark_db(
        self,
        task_id: str,
        status: str,
        name: str | None,
        *,
        error: str | None = None,
        progress: dict | None = None,
    ) -> None:
        extra = {"progress": progress} if progress is not None else None
        upsert_async_task_record("backtest", task_id, status, name=name, error=error, extra=extra)

    def _update_db_row(self, task_id: str, status: str) -> None:
        from backtest.models import BacktestTask

        try:
            from utils.db_session import use_db_session

            with use_db_session() as db:
                row = db.get(BacktestTask, task_id)
                if row is None:
                    return
                row.status = status
                if status in ("completed", "failed", "stopped"):
                    row.completed_at = datetime.now(UTC)
                db.commit()
        except Exception as exc:
            logger.error(f"[回测作业 {task_id}] 更新 backtest_tasks 状态失败: {exc}")


backtest_job_manager = BacktestJobManager()
