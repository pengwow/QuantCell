"""挖掘过程事件节流落库：工作线程内缓冲，按时间/条数批量 sink，终态强制 flush。

sink 由路由层提供（开短 session 调 MiningRunService.append_events）；
本类不依赖 DB，便于单测。flush 失败只 debug，不影响挖掘与在线 WS 事件。
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)

# (job_id, events)
EventSink = Callable[[str, list[dict[str, Any]]], None]


class EventFlusher:
    def __init__(self, sink: EventSink, interval: float = 2.0, max_buffer: int = 20):
        self._sink = sink
        self._interval = interval
        self._max_buffer = max_buffer
        self._buf: dict[str, list[dict[str, Any]]] = {}
        self._last: dict[str, float] = {}
        self._lock = threading.Lock()

    def add(self, job_id: str, evt: dict[str, Any]) -> None:
        with self._lock:
            self._buf.setdefault(job_id, []).append(evt)
            should = (
                len(self._buf[job_id]) >= self._max_buffer
                or time.monotonic() - self._last.get(job_id, 0.0) >= self._interval
            )
        if should:
            self.flush(job_id)

    def flush(self, job_id: str) -> None:
        with self._lock:
            evts = self._buf.pop(job_id, None)
            self._last[job_id] = time.monotonic()
        if not evts:
            return
        try:
            self._sink(job_id, evts)
        except Exception as e:
            logger.debug(f"挖掘事件落库失败（不影响任务）: {job_id} {e}")
