"""RL 训练作业的 worker 入口（M2 Task 10）。

训练主体 `RLService.train(config, reporter)` 留在 worker 进程里跑，本模块只做
两件事：
1. 提供跨进程 reporter（`SpoolReporter`）：进度写 JSON 快照、日志写 NDJSON
   事件流水、取消读 `.stop` 标志文件，父进程 relay 线程据此还原 TrainTask
2. 把训练结果收敛成 `JobResult`（父进程负责终态落库与通知）

worker 不写数据库、不持有 API 进程的 TrainTask；payload 只有可 JSON 化的训练配置。
"""

from __future__ import annotations

import os
import time
from typing import Any

from jobs import progress_spool
from jobs.spec import JobResult, JobSpec
from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)

#: 进度快照落盘最小间隔：训练回调每个 step 都会 state()，不节流会写爆磁盘
SNAPSHOT_INTERVAL_SECONDS = 0.5


class SpoolReporter:
    """worker 侧 reporter：实现训练代码依赖的 state/log/should_cancel/check_cancel。"""

    active = True

    def __init__(self, job_id: str, interval: float = SNAPSHOT_INTERVAL_SECONDS) -> None:
        self._job_id = job_id
        self._interval = interval
        self._last_flush = 0.0
        self._last = {"stage": None, "progress": None, "message": None}

    def state(self, *, stage: str | None = None, progress: float | None = None, message: str = "") -> None:
        now = time.monotonic()
        stage_changed = stage is not None and stage != self._last["stage"]
        # 同阶段内限频；换阶段立即落盘，前端能第一时间看到阶段切换
        if not stage_changed and now - self._last_flush < self._interval:
            return
        if stage is not None:
            self._last["stage"] = stage
        if progress is not None:
            self._last["progress"] = progress
        if message:
            self._last["message"] = message
        self.flush()

    def flush(self) -> None:
        self._last_flush = time.monotonic()
        progress_spool.write_snapshot(
            self._job_id,
            {
                "pid": os.getpid(),
                "ts": time.time(),
                "stage": self._last["stage"],
                "progress": self._last["progress"],
                "message": self._last["message"],
            },
        )

    def log(self, line: str) -> None:
        progress_spool.append_event(self._job_id, {"type": "log", "line": str(line)})

    def should_cancel(self) -> bool:
        return progress_spool.stop_requested(self._job_id)

    def check_cancel(self) -> None:
        if self.should_cancel():
            # 函数内 import 原因：TrainingCancelled 定义在 services.rl_task_runner，
            # 而 runner 会 import 本模块做投递，顶层导入形成循环
            from services.rl_task_runner import TrainingCancelled

            raise TrainingCancelled


def _rebuild_config(payload: dict[str, Any]) -> Any:
    """worker 内按 payload 重建训练配置（worker 只认 JSON，不接 pydantic 对象）。"""
    from services.rl_service import RLTrainConfig

    return RLTrainConfig(**payload)


def run_rl_train_job(spec: JobSpec) -> JobResult:
    job_id = spec.job_id
    reporter = SpoolReporter(job_id)
    progress_spool.bind_job(job_id)
    try:
        # 排队期间就被取消的任务：不打训练，直接回 cancelled
        if reporter.should_cancel():
            return JobResult(status="cancelled", result_ref=job_id)

        reporter.state(stage="starting", progress=0.0, message="训练任务启动")
        reporter.log("训练任务启动")

        # 重型依赖（torch / stable-baselines3）延迟到 worker 真正开跑时再加载
        from services.rl_service import RLService, rl_meta_path

        result = RLService().train(_rebuild_config(spec.payload["config"]), reporter=reporter)
        model_path = getattr(result, "model_path", None)
        reporter.state(stage="saving", progress=1.0, message="训练完成")
        return JobResult(
            status="succeeded",
            result_ref=job_id,
            metrics={
                "model_path": model_path,
                "meta_path": str(rl_meta_path(model_path)) if model_path else None,
            },
        )
    except Exception as exc:  # 任务边界：异常转成 JobResult，不抛给进程池
        if reporter.should_cancel():
            return JobResult(status="cancelled", result_ref=job_id)
        logger.error(f"[RLJob] {job_id} 训练失败: {exc}")
        return JobResult(status="failed", result_ref=job_id, error=f"{type(exc).__name__}: {exc}")
    finally:
        reporter.flush()
        progress_spool.unbind_job()
