"""HPO 单 trial 的进程池执行器。

optuna 的采样仍留在调用进程里串行推进（n_jobs=1），只把「一个 trial 的评估」
投到 BoundedJobPool 的 spawn worker 上跑：

- trial 不再占用 API / lifecycle 进程的时间片，可与其他作业并行；
- 采样顺序不因并行而改变，固定 seed 下与串行路径逐值一致。

负载刻意保持纯 JSON（symbol/interval/params/...），worker 侧用
BacktestDataProvider 重新加载 K 线再跑 BacktestLoop —— 不跨进程传 DataFrame
（spawn 无法 pickle 闭包），也不写数据库。
"""

from __future__ import annotations

import threading
import uuid
from typing import Any

from jobs import progress_spool
from jobs.pool import BoundedJobPool, JobPoolFullError, pool_resources
from jobs.spec import JobResult, JobSpec
from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.SYSTEM)

KIND = "hpo_trial"
#: 单个 trial 的等待上限；超过即放弃（optuna 侧把该 trial 记为剪枝）
DEFAULT_TIMEOUT_SECONDS = 600.0

_pool: BoundedJobPool | None = None
_pool_lock = threading.Lock()


def _job_pool() -> BoundedJobPool:
    """懒建本进程内的 trial 池（复用，不重复 spawn）。"""
    global _pool
    with _pool_lock:
        if _pool is None:
            max_workers, cores = pool_resources("hpo")
            _pool = BoundedJobPool(max_workers=max_workers, cores=cores)
        return _pool


def pool_status() -> dict[str, int | list[int]] | None:
    """只读池状态；池未创建时返回 None（观测接口不应因查询而建池）。"""
    pool = _pool
    return pool.status_counts() if pool is not None else None


def shutdown_pool() -> None:
    """应用退出时关闭 trial 池；未建池时为空操作。"""
    global _pool
    with _pool_lock:
        pool = _pool
        _pool = None
    if pool is not None:
        pool.shutdown(wait=False)


class TrialExecutionError(RuntimeError):
    """trial 在进程池内失败 / 超时。"""


def evaluate_trial_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """单 trial 纯计算，口径与 `BacktestEvaluator(metric=...)` 保持一致。

    非法参数（fast>=slow）或任何评估异常 → `-inf`（与 evaluator 的惩罚口径一致）；
    NaN 归零（evaluator 同样把 NaN 当 0）。

    返回 `{"value": float, "intermediate": [[step, value], ...]}`，中间值是
    权益曲线逐点，父进程用它回放 optuna report，保证串行/并行 intermediate 一致。
    """
    # 回测栈依赖较重，与 worker/lifecycle 一致延迟导入：父进程只拿执行器，
    # 不应该为了 import 本模块就把 pandas/axon_quant 拉起来
    from backtest.backtest_loop import BacktestLoop
    from backtest.data_provider import BacktestDataProvider
    from strategy.base import StrategyConfig
    from strategy.templates.dual_ma import DualMA

    params = dict(payload["params"])
    symbol = str(payload["symbol"])
    try:
        fast, slow = int(params["fast"]), int(params["slow"])
        if fast >= slow:
            raise ValueError(f"fast({fast}) 必须小于 slow({slow})")
        data = BacktestDataProvider().load_klines(symbol, str(payload["interval"]))
        strategy = DualMA(StrategyConfig(name="dual_ma", symbol=symbol, params={"fast": fast, "slow": slow}))
        result = BacktestLoop(initial_cash=float(payload.get("initial_cash", 100_000.0))).run(
            strategy=strategy,
            data=data,
            symbol=symbol,
        )
    except Exception as exc:  # 单 trial 失败不炸整个搜索，按 evaluator 口径记 -inf
        logger.warning(f"HPO trial 评估失败 params={params}: {exc}")
        return {"value": float("-inf"), "intermediate": []}

    value = float(getattr(result, str(payload.get("metric", "total_pnl")), 0.0) or 0.0)
    if value != value:  # NaN
        value = 0.0
    intermediate = [[step, float(point["equity"])] for step, point in enumerate(result.equity_curve)]
    return {"value": value, "intermediate": intermediate}


def run_hpo_trial_job(spec: JobSpec) -> JobResult:
    """worker 入口（模块级函数，可被 spawn 子进程重新导入）。"""
    # 排队期间被超时撤销的 trial 出队即退，不再白跑一轮完整回测
    if progress_spool.stop_requested(spec.job_id):
        return JobResult(status="interrupted", error="trial 在排队期间被取消")
    outcome = evaluate_trial_payload(spec.payload)
    return JobResult(status="succeeded", result_ref=spec.job_id, metrics=outcome)


class PoolTrialExecutor:
    """把 HPORunner 的单个 trial 投进进程池并阻塞等结果。

    阻塞是刻意的：采样在调用进程串行推进，trial 之间不会乱序，固定 seed 下
    结果与串行路径逐值可比（Task 11.2 的核心不变量）。

    `base_payload` 是 trial 的静态部分（symbol/interval/initial_cash/metric），
    每次调用只补 `params`。
    """

    def __init__(self, base_payload: dict[str, Any], *, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        self._base = dict(base_payload)
        self._timeout = float(timeout_seconds)

    def __call__(self, params: dict[str, Any]) -> tuple[float, list[tuple[int, float]]]:
        job_id = f"hpo-{uuid.uuid4().hex}"
        spec = JobSpec(job_id=job_id, kind=KIND, payload={**self._base, "params": dict(params)})

        done = threading.Event()
        box: dict[str, JobResult] = {}

        def _on_done(job_id: str, result: JobResult) -> None:
            box["result"] = result
            done.set()
            # 清理超时撤销路径写下的 .stop 标志，避免 spool 目录残留
            progress_spool.clear(job_id)

        pool = _job_pool()
        try:
            pool.submit(spec, _on_done)
        except JobPoolFullError as exc:
            raise TrialExecutionError(f"进程池已满，trial 未入池: {exc}") from exc

        if not done.wait(self._timeout):
            # 超时不能白占 worker：还在排队就直接从池里撤下；已派发的写 stop 标志，
            # worker 入口看到即退（回调里统一 clear spool 文件）。
            # ponytail: 已运行中的 trial 没有协作取消点（BacktestLoop 不支持中断），
            # 只能等它自然结束；升级路径是在评估循环里加取消检查。
            if not pool.cancel_queued(job_id):
                progress_spool.request_stop(job_id)
            raise TrialExecutionError(f"trial 超时（{self._timeout}s）")

        result = box["result"]
        if result.status != "succeeded":
            raise TrialExecutionError(result.error or f"trial 状态异常: {result.status}")

        metrics = result.metrics or {}
        intermediate = tuple((int(step), float(value)) for step, value in metrics.get("intermediate") or [])
        return float(metrics.get("value", float("-inf"))), list(intermediate)
