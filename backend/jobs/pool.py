"""有界 spawn 进程池：让 GIL 绑定的回测 / 训练真正并行。

设计要点：
- 活跃子进程数严格 ≤ max_workers：调度线程等到空槽位才 executor.submit，
  因此 queued / running 计数是准确的（不依赖 future.running() 轮询猜测）。
- 排队上限 max_pending：满了抛 JobPoolFullError，由调度层决定拒绝还是回写 queued。
- BrokenProcessPool（子进程被 kill -9）：重建 executor，并把所有非终态作业标记
  interrupted，避免整个池永久失效。
- worker 只做纯计算：结果经 JobResult 回传引用，数据库写入仍留在 API 进程。
"""

from __future__ import annotations

import multiprocessing
import os
import threading
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool

from config.settings import get_settings
from jobs.spec import JOB_STATUSES, JobResult, JobSpec
from jobs.worker_entry import init_worker, run_job
from utils.config_manager import get_flag, get_value
from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.SYSTEM)

# 回调参数用 (job_id, result)：池不保留 spec 本体，避免长生命周期内存占用
DoneCallback = Callable[[str, JobResult], None]


class JobPoolFullError(RuntimeError):
    """排队数超过上限；调用方应拒绝入池而不是阻塞 API 请求。"""


def parse_core_range(raw: str) -> list[int]:
    """解析绑核区间：支持 "4-15" / "4,6,8" / "4 6 8" 混写，空串返回 []。"""
    cores: list[int] = []
    for part in str(raw or "").replace(",", " ").split():
        if "-" in part:
            start_text, _, end_text = part.partition("-")
            start, end = int(start_text), int(end_text)
            if end < start:
                raise ValueError(f"绑核区间非法: {part}")
            cores.extend(range(start, end + 1))
        else:
            cores.append(int(part))
    return cores


def resolve_cores() -> list[int]:
    """绑核区间：settings（QUANTCELL_JOB_CORES）优先，其次 config.toml [jobs].cores。"""
    raw = get_settings().job_cores
    if raw is None:
        config_value = get_value("jobs.cores", "")
        raw = config_value if isinstance(config_value, str) else ""
    return parse_core_range(raw)


def pool_enabled() -> bool:
    """灰度开关：settings 显式配置（True/False）优先；未配置（None）回落 [jobs].enabled，默认关闭。

    三态是刻意的：bool 默认 False 会把「未设置」和「显式 false」混在一起，
    导致 config.toml 开了池之后环境变量关不掉。
    """
    configured = get_settings().job_pool_enabled
    if configured is not None:
        return configured
    return get_flag("jobs.enabled", False)


def default_max_workers(cores: list[int]) -> int:
    """默认并发：有绑核区间按核数；否则留一核给 API 进程。

    ponytail: 这是静态启发式，不做负载自适应；实测容量不足再引入按队列深度伸缩。
    """
    if cores:
        return len(cores)
    return max(1, (os.cpu_count() or 2) - 1)


def pool_resources(kind: str) -> tuple[int, list[int]]:
    """回测 / HPO 两池的并发与绑核预算，kind ∈ {"backtest", "hpo"}。

    配了绑核区间必须按池切分：两池若共用同一批核且各自 len(cores) 并发，
    会把 2*len(cores) 个 worker 绑到同一批核上互相抢占，绑核隔离形同虚设。
    未配置绑核时保持原默认（cpu-1），由 OS 统一调度；需要硬隔离就配 [jobs].cores。

    ponytail: 静态对半切分，不按实际负载动态调整；单核区间只能两池共享
    （各 1 并发，OS 分时）。升级路径是共享池 + 按 kind 配额调度。
    """
    cores = resolve_cores()
    if not cores:
        return default_max_workers([]), []
    if len(cores) == 1:
        return 1, list(cores)
    mid = (len(cores) + 1) // 2
    selected = cores[:mid] if kind == "backtest" else cores[mid:]
    return len(selected), selected


class BoundedJobPool:
    """有界 spawn 进程池（单调度线程 + ProcessPoolExecutor）。"""

    def __init__(
        self,
        max_workers: int | None = None,
        max_pending: int = 32,
        cores: list[int] | None = None,
    ) -> None:
        self._cores = list(cores or [])
        self.max_workers = int(max_workers or default_max_workers(self._cores))
        self.max_pending = max(1, int(max_pending))

        self._ctx = multiprocessing.get_context("spawn")
        # 共享计数器：每个 worker 启动时领取序号，把不同进程固定到不同核
        self._counter = self._ctx.Value("i", 0)
        self._executor = self._new_executor()

        self._condition = threading.Condition()
        self._pending: list[JobSpec] = []
        self._states: dict[str, str] = {}
        # 终态只留计数、不留 job_id：_states 若在终态后继续保留条目，长跑进程的
        # 内存会随作业数单调增长；观测口径由本计数器补齐（status_counts 合并透出）
        self._terminal_counts: dict[str, int] = {}
        self._callbacks: dict[str, DoneCallback | None] = {}
        self._running = 0
        self._generation = 0
        self._closed = False
        self._thread = threading.Thread(target=self._dispatch_loop, name="job-pool-dispatch", daemon=True)
        self._thread.start()

    # ------------------------------------------------------------------ 对外接口

    def submit(self, spec: JobSpec, on_done: DoneCallback | None = None) -> str:
        """入池排队；超出排队上限抛 JobPoolFullError，在途作业重复 job_id 抛 ValueError。

        终态后 job_id 即从 _states 清除，判重只覆盖在途作业；调用方需用全局唯一 id
        （task_id / uuid），避免与历史作业的 spool 文件混淆。
        """
        with self._condition:
            if self._closed:
                raise RuntimeError("作业池已关闭")
            if spec.job_id in self._states:
                raise ValueError(f"重复的 job_id: {spec.job_id}")
            if len(self._pending) >= self.max_pending:
                raise JobPoolFullError(f"作业池排队已满（上限 {self.max_pending}），拒收 {spec.job_id}")
            self._states[spec.job_id] = "queued"
            self._callbacks[spec.job_id] = on_done
            self._pending.append(spec)
            self._condition.notify_all()
        # 全链路日志统一格式 job_id=<id> event=<阶段>，单个 job_id 即可 grep 定位卡点
        logger.info(f"作业事件 job_id={spec.job_id} event=enqueue kind={spec.kind}")
        return spec.job_id

    def status_counts(self) -> dict[str, int | list[int]]:
        """队列可观测：各状态数量 + 并发/绑核配置（M3 的 /jobs/stats 直接透出）。"""
        with self._condition:
            counts: dict[str, int | list[int]] = {status: 0 for status in JOB_STATUSES}
            for status in self._states.values():
                counts[status] = int(counts.get(status, 0)) + 1
            for status, count in self._terminal_counts.items():
                counts[status] = int(counts.get(status, 0)) + count
            counts["max_workers"] = self.max_workers
            counts["cores"] = list(self._cores)
            # 排队上限一并透出：可观测接口据此判断「队列已满」是否正在阻断新作业
            counts["max_pending"] = self.max_pending
            return counts

    def shutdown(self, wait: bool = True) -> None:
        """关闭池：拒绝新作业，并在途作业按 interrupted 收尾。

        wait=False（应用退出路径）会额外 terminate 所有 worker：executor.shutdown
        只发退出哨兵，忙 worker 要跑完当前长任务才退，父进程退出后它们就成孤儿
        继续占核，必须在退出前显式杀掉。
        """
        with self._condition:
            if self._closed:
                return
            self._closed = True
            interrupted = []
            for spec in self._pending:
                self._mark_terminal(spec.job_id, "interrupted")
                interrupted.append((spec.job_id, self._callbacks.pop(spec.job_id, None)))
                logger.info(f"作业事件 job_id={spec.job_id} event=cancel reason=pool_shutdown")
            self._pending.clear()
            self._condition.notify_all()
        for job_id, callback in interrupted:
            if callback:
                # 关闭路径不能让某个回调的异常（如退出期 DB 已不可用）阻断后续
                # executor.shutdown / worker 清理，否则 worker 会变孤儿
                try:
                    callback(job_id, JobResult(status="interrupted", error="作业池关闭，任务未启动"))
                except Exception as exc:
                    logger.error(f"作业事件 job_id={job_id} 关闭回调失败: {exc}")
        self._thread.join(timeout=5)
        # executor.shutdown 会把 _processes 清空（实测 3.14 为 None），worker 列表必须提前取
        workers = [] if wait else list((getattr(self._executor, "_processes", None) or {}).values())
        self._executor.shutdown(wait=wait, cancel_futures=True)
        if not wait:
            self._terminate_workers(workers)

    def cancel_queued(self, job_id: str) -> bool:
        """撤销仍在排队的作业（按 interrupted 收尾并触发回调）；已派发则返回 False。

        运行中的作业不能单独 kill：那会触发 BrokenProcessPool 连坐整个池，
        运行中取消只能走协作式 stop 标志（见 progress_spool）。
        """
        with self._condition:
            for index, spec in enumerate(self._pending):
                if spec.job_id == job_id:
                    self._pending.pop(index)
                    break
            else:
                return False
            self._mark_terminal(job_id, "interrupted")
            callback = self._callbacks.pop(job_id, None)
            self._condition.notify_all()
        logger.info(f"作业事件 job_id={job_id} event=cancel reason=cancel_queued")
        if callback:
            callback(job_id, JobResult(status="interrupted", error="作业在排队期间被取消"))
        return True

    def _terminate_workers(self, processes: list) -> None:
        # ProcessPoolExecutor 没有公开的"立即终止 worker"接口，_processes 是有意触及的
        # 私有属性：仅用于应用退出路径，升级路径是标准库提供公共 terminate API
        for process in processes:
            try:
                process.terminate()
            except Exception:
                pass  # worker 已退出或句柄失效，退出路径无需再兜

    # ------------------------------------------------------------------ 内部实现

    def _new_executor(self) -> ProcessPoolExecutor:
        return ProcessPoolExecutor(
            max_workers=self.max_workers,
            mp_context=self._ctx,
            initializer=init_worker,
            initargs=(self._cores, self._counter),
        )

    def _dispatch_loop(self) -> None:
        while True:
            with self._condition:
                while not self._closed and (not self._pending or self._running >= self.max_workers):
                    self._condition.wait()
                if self._closed:
                    return
                spec = self._pending.pop(0)
                self._states[spec.job_id] = "running"
                self._running += 1
                generation = self._generation

            logger.info(f"作业事件 job_id={spec.job_id} event=start kind={spec.kind}")
            try:
                future = self._executor.submit(run_job, spec)
            except BrokenProcessPool, RuntimeError:
                self._recover(spec.job_id, "进程池已损坏，作业未启动")
                continue
            future.add_done_callback(lambda f, job_id=spec.job_id, gen=generation: self._finish(job_id, f, gen))

    def _finish(self, job_id: str, future: object, generation: int) -> None:
        with self._condition:
            if generation != self._generation:
                return  # 已被 _recover 统一按 interrupted 收尾
            self._running -= 1

        try:
            result = future.result()  # type: ignore[attr-defined]
        except BrokenProcessPool:
            if self._closed:
                # 关闭路径主动 terminate worker 属预期：不重建 executor，也不再回调
                # （在途作业的中断收尾由下次启动的补偿逻辑接管）
                return
            # 回调保留在 _callbacks 里，由 _recover 按 interrupted 统一通知
            self._recover(job_id, "worker 进程异常退出，作业被中断")
            return
        except Exception as exc:  # 反序列化失败等池级异常
            result = JobResult(status="failed", error=f"{type(exc).__name__}: {exc}")

        with self._condition:
            self._mark_terminal(job_id, result.status)
            callback = self._callbacks.pop(job_id, None)
            self._condition.notify_all()
        if result.status == "failed":
            logger.error(f"作业事件 job_id={job_id} event=fail error={result.error}")
        elif result.status == "cancelled":
            logger.info(f"作业事件 job_id={job_id} event=cancel")
        else:
            logger.info(f"作业事件 job_id={job_id} event=finish status={result.status}")
        if callback:
            callback(job_id, result)

    def _mark_terminal(self, job_id: str, status: str) -> None:
        """终态收尾：清掉在途状态、累计终态计数（调用方须持有 _condition）。"""
        self._states.pop(job_id, None)
        self._terminal_counts[status] = self._terminal_counts.get(status, 0) + 1

    def _recover(self, origin_job_id: str, error: str) -> None:
        """BrokenProcessPool 恢复：重建池并把所有非终态作业标记 interrupted。"""
        logger.error(f"作业池进程异常退出，重建中: {origin_job_id} ({error})")
        with self._condition:
            self._generation += 1
            old_executor = self._executor
            self._executor = self._new_executor()
            interrupted: list[tuple[str, DoneCallback | None]] = []
            for job_id, status in list(self._states.items()):
                if status in ("queued", "running"):
                    self._mark_terminal(job_id, "interrupted")
                    interrupted.append((job_id, self._callbacks.pop(job_id, None)))
                    logger.error(f"作业事件 job_id={job_id} event=interrupt error={error}")
            self._pending.clear()
            self._running = 0
            self._condition.notify_all()

        # 旧 executor 已损坏，丢弃即可。注意：_recover 可能运行在该 executor 自己的
        # 回调线程里（BrokenProcessPool 终止流程持有 _shutdown_lock），同步 shutdown
        # 会自锁，因此放到独立线程关闭。
        threading.Thread(
            target=old_executor.shutdown,
            kwargs={"wait": False, "cancel_futures": True},
            name="job-pool-retire",
            daemon=True,
        ).start()

        result = JobResult(status="interrupted", error=error)
        for job_id, callback in interrupted:
            if callback:
                callback(job_id, result)
