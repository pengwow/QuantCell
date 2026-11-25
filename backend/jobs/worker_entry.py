"""作业池 worker 入口：刻意不 import 任何应用外壳模块。

spawn 子进程会重新执行本模块顶层，因此这里只能做「进程自检 + 作业分发」：
不得 import main / core.lifespan / worker.strategy_manager / websocket.manager，
也不得构造数据库连接或单例。父进程投递的唯一入口是 run_job(spec)。

注意：payload 里的相对路径不可依赖 cwd（子进程 cwd 不保证），需要路径的作业
由父进程传入绝对路径。
"""

from __future__ import annotations

import importlib
import os
import time
from collections.abc import Callable
from typing import Any

from jobs.spec import JobResult, JobSpec
from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.SYSTEM)

# 作业类型 -> 处理函数；M1 起由各作业模块在导入时注册
_HANDLERS: dict[str, Callable[[JobSpec], JobResult]] = {}

# 重型作业懒加载表：backtest 会拉起 pandas/axon_quant 等，worker 只在真正跑该作业时
# 才付出导入成本（sleep 自检、未来轻量作业不受影响）
_LAZY_HANDLERS: dict[str, tuple[str, str]] = {
    "backtest": ("jobs.backtest_job", "run_backtest_job"),
    "rl_train": ("jobs.rl_train_job", "run_rl_train_job"),
    "hpo_trial": ("jobs.hpo_trial_job", "run_hpo_trial_job"),
}

# 当前 worker 绑定的物理核编号；None 表示未绑核（macOS / 未配置）
_BOUND_CORE: int | None = None

_THREAD_ENV_VARS = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS")

DoneHandler = Callable[[JobSpec], JobResult]


def register_handler(kind: str, handler: DoneHandler) -> None:
    """注册作业处理函数（必须是模块级函数，可被 spawn 子进程重新导入）。"""
    _HANDLERS[kind] = handler


def _resolve_handler(kind: str) -> DoneHandler | None:
    """优先取已注册 handler，否则按懒加载表 import 并缓存。"""
    handler = _HANDLERS.get(kind)
    if handler is not None:
        return handler
    target = _LAZY_HANDLERS.get(kind)
    if target is None:
        return None
    module_name, func_name = target
    handler = getattr(importlib.import_module(module_name), func_name)
    _HANDLERS[kind] = handler
    return handler


def _claim_worker_index(counter: Any) -> int:
    """从共享计数器领取 worker 序号，用于把不同进程固定到不同核上。"""
    if counter is None:
        return 0
    with counter.get_lock():
        index = counter.value
        counter.value += 1
    return index


def init_worker(cores: list[int], counter: Any = None) -> None:
    """子进程初始化（进程池 initializer）：线程收敛 + 绑核。

    环境变量在这里而不是模块顶层设置：父进程也会 import 本模块拿 run_job 引用，
    在顶层设置会污染 API 进程的 BLAS 线程数。
    """
    global _BOUND_CORE
    for name in _THREAD_ENV_VARS:
        os.environ[name] = "1"

    # 延迟导入：只有 worker 需要收敛 torch 线程数，父进程不为作业池付导入成本
    try:
        import torch

        torch.set_num_threads(1)
    except ImportError:
        pass

    if cores:
        core = cores[_claim_worker_index(counter) % len(cores)]
        set_affinity = getattr(os, "sched_setaffinity", None)  # macOS 无该接口
        if set_affinity is not None:
            try:
                # 一次设完整掩码（{core}），避免多核循环里被最后一核覆盖
                set_affinity(0, {core})
                _BOUND_CORE = core
            except OSError as exc:
                logger.warning(f"worker 绑核失败（core={core}）: {exc}")


def _sleep_job(spec: JobSpec) -> JobResult:
    """自检用最简作业：进程池准入、进程复用与绑核验证（测试 / 基线脚本使用）。

    payload.die=true 时直接退出进程，用于模拟 kill -9 验证 BrokenProcessPool 恢复。
    """
    if spec.payload.get("die"):
        os._exit(1)
    seconds = float(spec.payload.get("seconds", 0.05))
    time.sleep(seconds)
    return JobResult(status="succeeded", metrics={"seconds": seconds, "pid": os.getpid(), "core": _BOUND_CORE})


register_handler("sleep", _sleep_job)


def run_job(spec: JobSpec) -> JobResult:
    """进程池回调入口（模块级函数，可 pickle）。异常统一转 failed 终态。"""
    started = time.monotonic()
    handler = _resolve_handler(spec.kind)
    if handler is None:
        return JobResult(status="failed", error=f"未知作业类型: {spec.kind}")

    try:
        result = handler(spec)
    except Exception as exc:  # 子进程异常不能静默消失，必须回传终态
        logger.exception(f"作业执行失败: {spec.job_id} ({spec.kind})")
        return JobResult(status="failed", error=f"{type(exc).__name__}: {exc}")

    metrics = dict(result.metrics or {})
    metrics.setdefault("wall_seconds", round(time.monotonic() - started, 3))
    return JobResult(status=result.status, result_ref=result.result_ref, error=result.error, metrics=metrics)
