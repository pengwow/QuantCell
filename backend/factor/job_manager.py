"""因子分析异步任务管理：进程内单例、固定线程池、内存 TTL、WS 进度桥接。

结果只存内存（30 分钟 TTL），可回看研究产物由 factor 快照（P0-3）承担。
WS 推送只含状态/进度，不含结果大 payload；WS 不可用不影响任务执行。
"""

from __future__ import annotations

import asyncio
import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from utils.logger import LogType, get_logger
from websocket.manager import manager

logger = get_logger(__name__, LogType.APPLICATION)

MAX_EVENTS = 500

ProgressCb = Callable[[float, str, str], None]
EventCb = Callable[[str, str, "float | None", str], None]  # (level, stage, p, msg)
# submit 注入：manager 补 job_id 后调用 (job_id, level, stage, p, msg)
EventTerminalCb = Callable[[str, str, str, "float | None", str], None]
Runner = Callable[[ProgressCb, ProgressCb, "EventCb | None"], dict[str, Any]]
# (job_id, ok, payload)：ok=True 时 payload 为结果 dict，False 时为错误字符串
TerminalCb = Callable[[str, bool, "dict[str, Any] | str"], None]


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class FactorJob:
    job_id: str
    kind: str
    status: JobStatus = JobStatus.PENDING
    progress: float = 0.0
    stage: str = ""
    message: str = ""
    result: dict[str, Any] | None = None
    error: str | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class FactorJobManager:
    def __init__(self, ttl_seconds: float = 1800.0, sweep_interval: float = 300.0, max_workers: int = 4):
        self._jobs: dict[str, FactorJob] = {}
        self._lock = threading.Lock()
        self._ttl = ttl_seconds
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="factor-job")
        self._stop_sweep = threading.Event()
        self._sweeper = threading.Thread(target=self._sweep_loop, args=(sweep_interval,), daemon=True)
        self._sweeper.start()

    # ---------- 提交/执行 ----------

    def submit(
        self,
        kind: str,
        params: dict[str, Any],
        runner: Runner,
        on_terminal: TerminalCb | None = None,
        on_event_cb: EventTerminalCb | None = None,
    ) -> str:
        job_id = str(uuid.uuid4())
        job = FactorJob(job_id=job_id, kind=kind)
        with self._lock:
            self._jobs[job_id] = job
        self._emit(job)
        self._executor.submit(self._run, job, runner, on_terminal, on_event_cb)
        return job_id

    def _run(
        self,
        job: FactorJob,
        runner: Runner,
        on_terminal: TerminalCb | None = None,
        on_event_cb: EventTerminalCb | None = None,
    ) -> None:
        def on_progress(progress: float, stage: str = "", message: str = "") -> None:
            self._update(job.job_id, progress=progress, stage=stage, message=message)

        def on_event(level: str, stage: str, p: float | None, msg: str) -> None:
            # manager 自身不存事件：唯一存储/推 WS 点是路由侧 on_event_cb
            # （append_event + 节流落库），避免事件被累积两次、WS 推送两遍。
            # analyze/compare 不传 on_event_cb，这里直接空转。
            if on_event_cb is not None:
                try:
                    on_event_cb(job.job_id, level, stage, p, msg)
                except Exception:
                    logger.exception(f"事件回调执行失败: {job.job_id}")

        try:
            self._update(job.job_id, status=JobStatus.RUNNING, progress=0.0, stage="running")
            result = runner(on_progress, on_progress, on_event)
            with self._lock:
                job.result = result
            self._update(
                job.job_id,
                status=JobStatus.COMPLETED,
                progress=100.0,
                stage="completed",
                message="完成",
            )
            if on_terminal is not None:
                try:
                    on_terminal(job.job_id, True, result)
                except Exception:
                    # 落库等终态副作用失败不得影响内存任务状态
                    logger.exception(f"终态回调执行失败: {job.job_id}")
        except Exception as e:
            logger.exception(f"因子任务失败: {job.job_id}")
            self._update(job.job_id, status=JobStatus.FAILED, error=str(e), message="失败")
            if on_terminal is not None:
                try:
                    on_terminal(job.job_id, False, str(e))
                except Exception:
                    logger.exception(f"终态回调执行失败: {job.job_id}")

    # ---------- 查询 ----------

    def get(self, job_id: str) -> FactorJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def get_status(self, job_id: str) -> dict[str, Any] | None:
        job = self.get(job_id)
        if job is None:
            return None
        return {
            "job_id": job.job_id,
            "kind": job.kind,
            "status": str(job.status),
            "progress": job.progress,
            "stage": job.stage,
            "message": job.message,
            "error": job.error,
            "created_at": job.created_at.isoformat(),
            "updated_at": job.updated_at.isoformat(),
        }

    def get_result(self, job_id: str) -> dict[str, Any] | None:
        job = self.get(job_id)
        return job.result if job else None

    def append_event(self, job_id: str, level: str, stage: str, p: float | None, msg: str) -> dict[str, Any] | None:
        """累积一条过程事件并推 WS；job 不存在返回 None。

        idx 按创建序号全局递增；超过 MAX_EVENTS 删除最旧（FIFO），idx 不回收。
        p 非空时顺带把进度取 max 推进，保证状态消息与事件一致、百分比不回退。
        """
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            evt = {
                "idx": (job.events[-1]["idx"] + 1) if job.events else 0,
                "ts": datetime.now(UTC).isoformat(),
                "level": level,
                "stage": stage,
                "msg": msg,
                "p": p,
            }
            job.events.append(evt)
            if len(job.events) > MAX_EVENTS:
                del job.events[: len(job.events) - MAX_EVENTS]
            if p is not None and p > job.progress:
                job.progress = p
                job.stage = stage
                job.message = msg
            job.updated_at = datetime.now(UTC)
        self._emit_event(job_id, evt)
        return evt

    def get_events(self, job_id: str, after_idx: int = 0) -> dict[str, Any] | None:
        job = self.get(job_id)
        if job is None:
            return None
        with self._lock:
            evts = [dict(e) for e in job.events if e["idx"] >= after_idx]
            next_idx = job.events[-1]["idx"] + 1 if job.events else 0
        return {"events": evts, "next_idx": next_idx}

    # ---------- 内部 ----------

    def _update(self, job_id: str, **fields: Any) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            for k, v in fields.items():
                setattr(job, k, v)
            job.updated_at = datetime.now(UTC)
            snapshot = job
        self._emit(snapshot)

    def _emit(self, job: FactorJob) -> None:
        try:
            if getattr(manager, "message_queue", None) is None:
                return
            message = {
                "type": "factor:job",
                "id": f"factorjob_{job.job_id}",
                "timestamp": int(time.time() * 1000),
                "data": {
                    "job_id": job.job_id,
                    "type": "progress",
                    "kind": job.kind,
                    "status": str(job.status),
                    "progress": job.progress,
                    "stage": job.stage,
                    "message": job.message,
                    "error": job.error,
                },
            }
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(manager.queue_message(message, topic="factor:job"))
                else:
                    loop.run_until_complete(manager.queue_message(message, topic="factor:job"))
            except RuntimeError:
                asyncio.run(manager.queue_message(message, topic="factor:job"))
        except Exception as e:
            logger.debug(f"factor:job WS 推送跳过: {e}")

    def _emit_event(self, job_id: str, evt: dict[str, Any]) -> None:
        try:
            if getattr(manager, "message_queue", None) is None:
                return
            message = {
                "type": "factor:job",
                "id": f"factorjob_evt_{job_id}_{evt['idx']}",
                "timestamp": int(time.time() * 1000),
                "data": {"job_id": job_id, "type": "event", "event": evt},
            }
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(manager.queue_message(message, topic="factor:job"))
                else:
                    loop.run_until_complete(manager.queue_message(message, topic="factor:job"))
            except RuntimeError:
                asyncio.run(manager.queue_message(message, topic="factor:job"))
        except Exception as e:
            logger.debug(f"factor:job 事件 WS 推送跳过: {e}")

    def shutdown(self) -> None:
        """关闭线程池和扫尾线程（应用退出时调用）"""
        # 先通知扫尾线程停止
        self._stop_sweep.set()
        # 关闭线程池，wait=False 避免阻塞主线程
        self._executor.shutdown(wait=False)
        logger.info("FactorJobManager 已关闭（线程池 + 扫尾线程）")

    def _sweep_loop(self, interval: float) -> None:
        while not self._stop_sweep.wait(interval):
            try:
                now = datetime.now(UTC)
                with self._lock:
                    expired = [
                        jid
                        for jid, job in self._jobs.items()
                        if job.status in (JobStatus.COMPLETED, JobStatus.FAILED)
                        and (now - job.updated_at).total_seconds() > self._ttl
                    ]
                    for jid in expired:
                        del self._jobs[jid]
                if expired:
                    logger.info(f"清理过期因子任务 {len(expired)} 个")
            except Exception as e:
                logger.error(f"因子任务清理失败: {e}")


job_manager = FactorJobManager()
