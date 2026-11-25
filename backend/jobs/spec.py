"""作业数据契约：父进程与 worker 之间只传纯 JSON 数据。

P0 多进程作业池的边界约定：
- JobSpec.payload / resources 只能是 dict/list/str/int/float/bool/None，
  保证 spawn 子进程反序列化后不携带父进程的数据库连接、Session、闭包等状态。
- JobResult 只回传引用（result_ref）和指标，大结果由子进程落盘、父进程按引用读取。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

# 任务状态全集，与 async_task_records.status 的取值保持一致
JOB_STATUSES = ("queued", "running", "succeeded", "failed", "cancelled", "interrupted")
TERMINAL_JOB_STATUSES = ("succeeded", "failed", "cancelled", "interrupted")

_JSON_SCALARS = (str, int, float, bool, type(None))


def _assert_jsonable(value: Any, path: str) -> None:
    """递归校验只含 JSON 值；出现对象/函数/Session 时立刻报错。

    在构造期校验而不是投递期：错误信息能直接指到非法字段，且不会把
    不可序列化对象带进进程池队列（spawn 那儿报错会变成难查的 pickling error）。
    """
    if isinstance(value, _JSON_SCALARS):
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{path} 的键必须是字符串，实际为 {type(key).__name__}")
            _assert_jsonable(item, f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _assert_jsonable(item, f"{path}[{index}]")
        return
    raise TypeError(f"{path} 含不可序列化对象 {type(value).__name__}；作业参数必须是纯 JSON 数据")


@dataclass(frozen=True)
class JobSpec:
    """投递给 worker 的纯数据作业描述。"""

    job_id: str
    kind: str
    payload: dict[str, Any] = field(default_factory=dict)
    resources: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.job_id:
            raise ValueError("job_id 不能为空")
        if not self.kind:
            raise ValueError("kind 不能为空")
        if not isinstance(self.payload, dict) or not isinstance(self.resources, dict):
            raise TypeError("payload/resources 必须是 dict")
        _assert_jsonable(self.payload, "payload")
        _assert_jsonable(self.resources, "resources")

    @property
    def cores(self) -> int:
        """该作业期望的核数（M0 仅用于排队计费，默认 1）。"""
        value = self.resources.get("cores", 1)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"resources.cores 必须是正整数，实际为 {value!r}")
        return value

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "kind": self.kind,
            "payload": self.payload,
            "resources": self.resources,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> JobSpec:
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("JobSpec JSON 必须是对象")
        return cls(
            job_id=data.get("job_id", ""),
            kind=data.get("kind", ""),
            payload=data.get("payload") or {},
            resources=data.get("resources") or {},
        )


@dataclass(frozen=True)
class JobResult:
    """worker 回传的终态结果（只含引用与指标，不含业务数据本体）。"""

    status: str
    result_ref: str | None = None
    error: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in TERMINAL_JOB_STATUSES:
            raise ValueError(f"非法作业终态: {self.status}")
        _assert_jsonable(self.metrics, "metrics")

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "result_ref": self.result_ref,
            "error": self.error,
            "metrics": self.metrics,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JobResult:
        return cls(
            status=str(data.get("status", "")),
            result_ref=data.get("result_ref"),
            error=data.get("error"),
            metrics=data.get("metrics") or {},
        )
