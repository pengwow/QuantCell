"""P0 多进程作业池：有界 spawn 进程池 + 纯数据作业契约。

对外只暴露这些符号，业务侧（回测 / 训练 / 搜索）通过 JobSpec 投递、按
JobResult 收尾，不直接接触 multiprocessing 细节。
"""

from jobs.pool import (
    BoundedJobPool,
    JobPoolFullError,
    default_max_workers,
    parse_core_range,
    pool_enabled,
    resolve_cores,
)
from jobs.spec import JOB_STATUSES, TERMINAL_JOB_STATUSES, JobResult, JobSpec

__all__ = [
    "JOB_STATUSES",
    "TERMINAL_JOB_STATUSES",
    "BoundedJobPool",
    "JobPoolFullError",
    "JobResult",
    "JobSpec",
    "default_max_workers",
    "parse_core_range",
    "pool_enabled",
    "resolve_cores",
]
