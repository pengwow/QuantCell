"""作业池队列观测接口（M3 Task 12）。

`GET /api/v1/jobs/queue` 聚合三个进程池的 `status_counts()`，回答三个问题：
- 现在有多少作业在排队 / 运行；
- 绑定了几颗核（不绑核时为 0）；
- 是否有东西正在阻断新作业（池满 / 灰度关闭）。

只读语义：查询本身**不创建**进程池，未初始化的池按 0 计并标记 `created=false`，
避免「看一眼监控就 spawn 一堆 worker」。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from common.schemas import ApiResponse
from jobs.backtest_manager import backtest_job_manager
from jobs.hpo_trial_job import pool_status as hpo_pool_status
from jobs.pool import pool_enabled, resolve_cores
from services.rl_task_runner import pool_status as rl_pool_status

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


def queue_snapshot() -> dict[str, Any]:
    """聚合各池状态；顶层是汇总值，`pools` 保留分池明细便于定位。"""
    pools: dict[str, tuple[str, dict[str, int | list[int]] | None]] = {
        "backtest": ("回测", backtest_job_manager.pool_status()),
        "rl_train": ("RL 训练", rl_pool_status()),
        "hpo_trial": ("HPO 搜索", hpo_pool_status()),
    }

    queued = 0
    running = 0
    cores: set[int] = set()
    blocked: list[str] = []
    detail: dict[str, Any] = {}

    for name, (label, counts) in pools.items():
        if counts is None:
            detail[name] = {"created": False, "queued": 0, "running": 0, "max_workers": None, "cores": []}
            continue

        pool_queued = int(counts.get("queued", 0))
        queued += pool_queued
        running += int(counts.get("running", 0))
        pool_cores = list(counts.get("cores") or [])
        cores.update(pool_cores)

        # 排队数达到上限时，池会直接拒绝新作业 —— 这正是需要暴露的阻断原因
        max_pending = int(counts.get("max_pending") or 0)
        full = max_pending > 0 and pool_queued >= max_pending
        if full:
            blocked.append(f"{label}队列已满（{pool_queued}/{max_pending}），新作业会被拒绝")

        detail[name] = {
            "created": True,
            "queued": pool_queued,
            "running": int(counts.get("running", 0)),
            "max_workers": counts.get("max_workers"),
            "cores": pool_cores,
            "blocked": full,
        }

    if not pool_enabled():
        blocked.insert(0, "进程池未启用（[jobs].enabled=false），作业仍走线程/同步路径")

    # 未建池时按配置推算绑核数，保证「已绑核数」始终反映部署配置
    bound_cores = len(cores) if cores else len(resolve_cores())
    return {
        "queued": queued,
        "running": running,
        "cores": bound_cores,
        "blocked": blocked,
        "pools": detail,
    }


@router.get(
    "/queue",
    response_model=ApiResponse,
    summary="作业池队列观测",
    description="返回各进程池的排队 / 运行作业数、绑定核数与当前阻断原因；查询不会创建池。",
)
def get_job_queue() -> ApiResponse:
    return ApiResponse(code=0, message="操作成功", data=queue_snapshot())
