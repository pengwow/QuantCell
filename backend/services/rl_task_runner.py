"""RL 训练任务化 runner：进程内任务注册表 + 进度/日志事件源。

前端契约（字段名钉死，不要改名）：

- `POST /api/v1/rl/train/async` → 202 `{task_id, status: "queued"}`
- `GET  /api/v1/rl/train/{task_id}` → 快照
  `{task_id,status,stage,progress,message,error,model_path,meta_path,elapsed_ms}`
- `GET  /api/v1/rl/train/{task_id}/events` → SSE：`state`（快照）/ `log`（单行）/ 15s `: ping`
- `POST /api/v1/rl/train/{task_id}/cancel` → 协作式取消

训练侧通过 duck-typed reporter 上报（`state` / `log` / `should_cancel` /
`check_cancel`），`RLService.train(config, reporter=...)` 与
`RLWalkForwardService.validate(..., reporter=...)` 只依赖这四个方法，
runner 不在训练代码里做 import。

已知取舍：任务表是**进程内内存**（`_tasks`），进程重启即丢历史，不做 DB 落库。
ponytail: 并发全局=1（`_worker_lock` 串行化），后到的任务停在 `queued` 等前一个
跑完。天花板是「同一时刻只能跑一个训练任务 + 单进程可见」；升级路径是换成
独立任务队列进程（arq / celery / redis 队列），本文件退化为提交 / 查询 / 流式
读取的适配层，训练侧的 reporter 协议不用变。
"""

from __future__ import annotations

import contextlib
import json
import queue
import threading
import time
import uuid
from collections import deque
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)

TERMINAL_STATUSES = frozenset({"done", "error", "cancelled"})

#: SSE 心跳间隔：中间层（nginx / 网关）默认 60s 掐空闲连接，15s 一条注释行留余量
SSE_PING_SECONDS = 15.0
#: 每任务保留的日志行数（新订阅者补发，重连不丢上下文；更早的丢弃）
_LOG_TAIL = 200
#: learn() 分块数：块间检查取消标志，保证秒级取消响应
LEARN_CHUNKS = 8
#: 单块最小步数：SB3 的 learn 按 rollout 向上取整，块太小会让总步数成倍膨胀
_MIN_CHUNK_STEPS = 1_000
#: 进度广播阈值：每涨 0.5% 推一次 state，避免逐 step 刷爆 SSE
_STATE_MIN_DELTA = 0.005


class TrainingCancelled(Exception):
    """协作式取消信号：在阶段边界 / 进度回调处抛出。"""


class NullReporter:
    """无任务上下文的空上报器（同步 /train 路径用）。"""

    active = False

    def state(self, *, stage: str | None = None, progress: float | None = None, message: str = "") -> None: ...

    def log(self, line: str) -> None: ...

    def should_cancel(self) -> bool:
        return False

    def check_cancel(self) -> None: ...


class ScaledReporter:
    """子阶段 0..1 进度 → 父阶段区间 [base, base+span]，进度对前端仍是单一数值。"""

    def __init__(self, inner: Any, *, base: float, span: float):
        self._inner = inner
        self._base = float(base)
        self._span = float(span)

    @property
    def active(self) -> bool:
        return bool(getattr(self._inner, "active", False))

    def state(self, *, stage: str | None = None, progress: float | None = None, message: str = "") -> None:
        abs_progress = None if progress is None else self._base + self._span * float(progress)
        self._inner.state(stage=stage, progress=abs_progress, message=message)

    def log(self, line: str) -> None:
        self._inner.log(line)

    def should_cancel(self) -> bool:
        return bool(self._inner.should_cancel())

    def check_cancel(self) -> None:
        if self.should_cancel():
            raise TrainingCancelled


@dataclass
class TrainTask:
    """单个训练任务的状态 + SSE 订阅者集合。

    同时充当训练侧的 reporter：`state()` 更新快照并按阈值广播，
    `log()` 追加日志行并广播，`check_cancel()` 在阶段边界抛取消信号。
    """

    task_id: str
    status: str = "queued"
    stage: str = "queued"
    progress: float = 0.0
    message: str = ""
    error: str | None = None
    model_path: str | None = None
    meta_path: str | None = None
    created_at: float = field(default_factory=time.monotonic)
    started_at: float | None = None
    finished_at: float | None = None
    active: bool = True

    cancel_event: threading.Event = field(default_factory=threading.Event)
    subscribers: list[queue.Queue] = field(default_factory=list)
    log_tail: deque[str] = field(default_factory=lambda: deque(maxlen=_LOG_TAIL))
    lock: threading.Lock = field(default_factory=threading.Lock)

    # ---- 查询 ----

    @property
    def terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            end = self.finished_at or time.monotonic()
            return {
                "task_id": self.task_id,
                "status": self.status,
                "stage": self.stage,
                "progress": round(self.progress, 4),
                "message": self.message,
                "error": self.error,
                "model_path": self.model_path,
                "meta_path": self.meta_path,
                "elapsed_ms": int((end - self.created_at) * 1000),
            }

    # ---- reporter 协议 ----

    def state(self, *, stage: str | None = None, progress: float | None = None, message: str = "") -> None:
        changed = False
        with self.lock:
            stage_changed = stage is not None and stage != self.stage
            if stage_changed:
                self.stage = stage
                changed = True
            if progress is not None:
                p = min(1.0, max(0.0, float(progress)))
                advanced = p - self.progress  # 进度单调不回退：分块 / 折的回跳不闪前端
                # 阶段内按阈值节流；换阶段时第一跳就推（前端据此切换展示文案）
                if advanced >= _STATE_MIN_DELTA or (advanced > 0 and stage_changed):
                    self.progress = p
                    changed = True
            if message and message != self.message:
                self.message = message
                changed = True
        if changed:
            self._broadcast_state()

    def log(self, line: str) -> None:
        text = str(line).rstrip("\n")
        with self.lock:
            self.log_tail.append(text)
        self._broadcast({"event": "log", "data": text})

    def should_cancel(self) -> bool:
        return self.cancel_event.is_set()

    def check_cancel(self) -> None:
        if self.cancel_event.is_set():
            raise TrainingCancelled

    # ---- SSE 订阅 ----

    def subscribe(self) -> tuple[queue.Queue, list[str]]:
        q: queue.Queue = queue.Queue(maxsize=256)
        with self.lock:
            backlog = list(self.log_tail)
            self.subscribers.append(q)
        return q, backlog

    def unsubscribe(self, q: queue.Queue) -> None:
        with self.lock:
            with contextlib.suppress(ValueError):
                self.subscribers.remove(q)

    def _broadcast(self, event: dict[str, Any]) -> None:
        with self.lock:
            targets = list(self.subscribers)
        for q in targets:
            # 慢客户端丢事件而不是让训练线程阻塞（快照可重取，日志行可容忍丢失）
            with contextlib.suppress(queue.Full):
                q.put_nowait(event)

    def _broadcast_state(self) -> None:
        self._broadcast({"event": "state", "data": self.snapshot()})


_tasks: dict[str, TrainTask] = {}
_registry_lock = threading.Lock()
#: 全局并发=1：真正的串行化在这里，排队任务停在 queued
_worker_lock = threading.Lock()


def get_task(task_id: str) -> TrainTask | None:
    with _registry_lock:
        return _tasks.get(task_id)


def list_tasks() -> list[dict[str, Any]]:
    with _registry_lock:
        tasks = list(_tasks.values())
    return [t.snapshot() for t in tasks]


def reset_tasks() -> None:
    """测试专用：清空进程内任务表（生产无调用方）。"""
    with _registry_lock:
        _tasks.clear()


def submit_train_task(config: Any, *, train_fn: Callable[[Any, Any], Any] | None = None) -> str:
    """登记任务并起工作线程，立即返回 task_id（status=queued）。

    `train_fn(config, reporter) -> RLTrainResult` 可注入（测试用假训练替代真实 SB3）。
    """
    task = TrainTask(task_id=f"rltrain_{uuid.uuid4().hex[:12]}")
    with _registry_lock:
        _tasks[task.task_id] = task
    runner = train_fn or _default_train
    threading.Thread(
        target=_run_task,
        args=(task, config, runner),
        name=f"rl-train-{task.task_id}",
        daemon=True,
    ).start()
    return task.task_id


def cancel_task(task_id: str) -> bool:
    """请求取消；任务已终态返回 False（路由映射 409）。

    运行中的任务只置标志，真正停下发生在下一个阶段边界 / 进度回调；
    排队未开跑的任务直接标 cancelled（工作线程拿到锁后会跳过）。
    """
    task = get_task(task_id)
    if task is None:
        raise KeyError(task_id)
    queued_abort = False
    with task.lock:
        if task.terminal:
            return False
        task.cancel_event.set()
        if task.status == "queued":
            task.status = "cancelled"
            task.stage = "cancelled"
            task.message = "已取消（未开始训练）"
            task.finished_at = time.monotonic()
            queued_abort = True
    if queued_abort:
        task._broadcast_state()
    else:
        task.log("收到取消请求，将在当前阶段边界停止")
    return True


def sse_stream(task: TrainTask) -> Iterator[str]:
    """SSE 字节流：先发当前快照与日志历史，再逐事件转发；终态后关闭。

    Starlette 会把同步生成器丢进线程池迭代，`queue.get` 阻塞不会卡事件循环。
    """
    q, backlog = task.subscribe()
    try:
        yield _sse_frame("state", task.snapshot())
        for line in backlog:
            yield _sse_frame("log", line)
        if task.terminal:
            return
        while True:
            try:
                event = q.get(timeout=SSE_PING_SECONDS)
            except queue.Empty:
                yield ": ping\n\n"
                if task.terminal:
                    return
                continue
            yield _sse_frame(event["event"], event["data"])
            if event["event"] == "state" and event["data"].get("status") in TERMINAL_STATUSES:
                return
    finally:
        task.unsubscribe(q)


def _sse_frame(event: str, data: Any) -> str:
    if isinstance(data, dict):
        payload = json.dumps(data, ensure_ascii=False)
    else:
        # 日志必须单行：换行会破坏 SSE 帧边界
        payload = str(data).replace("\r", "").replace("\n", "\\n")
    return f"event: {event}\ndata: {payload}\n\n"


def _default_train(config: Any, reporter: Any) -> Any:
    from services.rl_service import RLService

    return RLService().train(config, reporter=reporter)


def _run_task(task: TrainTask, config: Any, train_fn: Callable[[Any, Any], Any]) -> None:
    with _worker_lock:
        if task.cancel_event.is_set():
            _finish(task, "cancelled", message="已取消（未开始训练）")
            return
        with task.lock:
            task.status = "running"
            task.started_at = time.monotonic()
        task.state(stage="starting", progress=0.0, message="训练任务启动")
        task.log("训练任务启动")
        try:
            result = train_fn(config, task)
        except TrainingCancelled:
            _finish(task, "cancelled", message="训练已取消")
        except Exception as exc:  # 任务边界：异常转成任务状态，不让线程静默死掉
            logger.error(f"[RLTask] {task.task_id} 训练失败: {exc}")
            _finish(task, "error", error=f"{type(exc).__name__}: {exc}", message="训练失败")
        else:
            model_path = getattr(result, "model_path", None)
            _finish(
                task,
                "done",
                progress=1.0,
                message="训练完成",
                model_path=model_path,
                meta_path=_meta_path_of(model_path),
            )


def _meta_path_of(model_path: str | None) -> str | None:
    if not model_path:
        return None
    # 旁车命名唯一来源在 rl_service.rl_meta_path，这里复用避免手抄扩展名
    from services.rl_service import rl_meta_path

    return str(rl_meta_path(model_path))


def _finish(
    task: TrainTask,
    status: str,
    *,
    progress: float | None = None,
    message: str = "",
    error: str | None = None,
    model_path: str | None = None,
    meta_path: str | None = None,
) -> None:
    with task.lock:
        if task.status in TERMINAL_STATUSES:
            return  # 已由 cancel 直接落终态，不重复广播
        task.status = status
        task.stage = status
        if progress is not None:
            task.progress = progress
        task.message = message or task.message
        task.error = error
        task.model_path = model_path or task.model_path
        task.meta_path = meta_path or task.meta_path
        task.finished_at = time.monotonic()
        task.active = False
    task._broadcast_state()
    task.log(f"任务结束: {status}")


# ---------------------------------------------------------------------------
# 分块训练：进度上报 + 取消粒度
# ---------------------------------------------------------------------------


def learn_in_chunks(model: Any, total_timesteps: int, reporter: Any, *, stage: str = "learning") -> None:
    """分块 `learn()`，块间检查取消标志；块内由 BaseCallback 逐 step 上报进度。

    `reporter` 非任务态（NullReporter，同步 /train 路径）时退化为单次 `learn`，
    保证 ModelHub 既有同步训练语义零漂移。

    ponytail: 最多 8 块、且单块不少于 `_MIN_CHUNK_STEPS`（小任务退化为 1~2 块，
    避免 SB3 按 rollout 向上取整把总步数成倍放大）；块越小取消越灵敏，
    但每次 `learn` 有少量 setup 开销。分块后总步数仍可能略超
    `total_timesteps`（与单次调用行为一致）。
    """
    total = max(1, int(total_timesteps))
    if not getattr(reporter, "active", False):
        model.learn(total_timesteps=total)
        return

    n_chunks = max(1, min(LEARN_CHUNKS, total // _MIN_CHUNK_STEPS))
    done = 0
    for i in range(n_chunks):
        reporter.check_cancel()
        steps = max(1, (total - done) // (n_chunks - i))
        model.learn(
            total_timesteps=steps,
            reset_num_timesteps=False,
            callback=_progress_callback(reporter, stage, done_before=done, total=total),
        )
        done += steps
        reporter.state(stage=stage, progress=done / total, message=f"训练进度 {done}/{total}")


def _progress_callback(reporter: Any, stage: str, *, done_before: int, total: int) -> Any:
    """SB3 BaseCallback：逐 step 上报区间进度，并在 step 粒度响应取消。"""
    try:
        from stable_baselines3.common.callbacks import BaseCallback
    except ImportError:  # SB3 缺失时 learn 本身会失败，这里只是别提前炸
        return None

    class _TaskProgressCallback(BaseCallback):
        def __init__(self):
            super().__init__()
            self._steps = 0

        def _on_step(self) -> bool:
            self._steps += 1
            reporter.check_cancel()  # TrainingCancelled 直接冒出 learn()
            reporter.state(stage=stage, progress=(done_before + self._steps) / total)
            return True

    return _TaskProgressCallback()
