"""作业进度回传通道（worker → API 进程）。

进程池 worker 不允许写数据库，multiprocessing.Queue 也不能塞进 JobSpec
（Queue 只能随进程创建时继承，作为 submit 参数 pickle 会直接报错）。这里用
「每作业一个 JSON 快照文件」做回传：worker 限频原子写入，API 进程的 relay
线程读取后更新内存进度并落库。

ponytail: 单机共享文件系统够用；将来要跨节点执行需换成消息队列或对象存储。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# 默认目录与回测任务文件同级，便于诊断时一起查看
_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "job_progress"

# 当前 worker 进程绑定的作业 id；None 表示当前进程不是作业 worker（如 API 进程）
_BOUND_JOB_ID: str | None = None


def progress_dir() -> Path:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    return _DATA_DIR


def snapshot_path(job_id: str) -> Path:
    return progress_dir() / f"{job_id}.json"


def stop_flag_path(job_id: str) -> Path:
    return progress_dir() / f"{job_id}.stop"


def events_path(job_id: str) -> Path:
    """追加式事件流水（RL 训练的日志行）：父进程按字节偏移增量读取。"""
    return progress_dir() / f"{job_id}.events"


def write_snapshot(job_id: str, payload: dict[str, Any]) -> None:
    """原子写快照：父进程读到的永远是完整 JSON，不会读到写了一半的内容。"""
    path = snapshot_path(job_id)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, default=str), encoding="utf-8")
    os.replace(tmp, path)


def read_snapshot(job_id: str) -> dict[str, Any] | None:
    try:
        return json.loads(snapshot_path(job_id).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def request_stop(job_id: str) -> None:
    """API 进程侧投递取消意图，worker 的取消令牌每 bar 检查该文件。"""
    stop_flag_path(job_id).touch()


def append_event(job_id: str, payload: dict[str, Any]) -> None:
    """追加一行 NDJSON 事件（日志类），失败静默——日志丢行不能拖垮训练。"""
    try:
        with events_path(job_id).open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
    except OSError:
        pass


def read_events(job_id: str, offset: int) -> tuple[list[dict[str, Any]], int]:
    """从字节偏移增量读取事件行，返回 (事件列表, 新偏移)。

    只消费以换行结尾的完整行：worker 正在写的半行留到下次读取，避免
    父进程解析到截断的 JSON。
    """
    try:
        raw = events_path(job_id).read_bytes()
    except FileNotFoundError:
        return [], offset
    chunk = raw[offset:]
    end = chunk.rfind(b"\n") + 1
    if end <= 0:
        return [], offset
    events: list[dict[str, Any]] = []
    for line in chunk[:end].decode("utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events, offset + end


def stop_requested(job_id: str) -> bool:
    return stop_flag_path(job_id).exists()


def clear(job_id: str) -> None:
    """清理作业的进度快照、事件流水与取消标志（作业终态收尾时调用）。"""
    for path in (snapshot_path(job_id), events_path(job_id), stop_flag_path(job_id)):
        path.unlink(missing_ok=True)


def bind_job(job_id: str) -> None:
    """worker 进程登记当前作业，供 stop_control 生成跨进程取消令牌。"""
    global _BOUND_JOB_ID
    _BOUND_JOB_ID = job_id


def unbind_job() -> None:
    global _BOUND_JOB_ID
    _BOUND_JOB_ID = None


class CrossProcessStopEvent:
    """取消令牌：本地 Event + 跨进程标志文件双读。

    API 进程调 request_stop 写文件，worker 在 is_set() 时多读一次文件，
    这样取消意图不需要再额外开一条 IPC 通道。
    """

    def __init__(self, event: Any, flag_path: Path) -> None:
        self._event = event
        self._flag_path = flag_path

    def is_set(self) -> bool:
        return self._event.is_set() or self._flag_path.exists()

    def set(self) -> None:
        self._event.set()

    def clear(self) -> None:
        self._event.clear()

    def wait(self, timeout: float | None = None) -> bool:
        return self._event.wait(timeout)


def bound_stop_event(event: Any) -> Any:
    """非 worker 进程原样返回本地 Event，保持旧路径行为不变。"""
    if _BOUND_JOB_ID is None:
        return event
    return CrossProcessStopEvent(event, stop_flag_path(_BOUND_JOB_ID))
