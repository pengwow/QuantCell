"""回测协作式取消注册表

回测在 daemon 线程中 fire-and-forget 执行，stop 端点无法杀线程。
用进程内 {task_id: Event} 注册表把「停止指令」投递给执行线程，
执行侧在每个品种开跑前检查令牌，置位即抛 BacktestCancelled 走「已终止」收尾。

边界（ponytail）：单品种的回测循环是单次阻塞调用，中途无法中断，
stop 只在品种边界生效。升级路径：pyo3 取消通道让内核逐 bar 感知取消。
"""

from __future__ import annotations

import threading


class BacktestCancelled(Exception):
    """停止令牌置位后由执行线程抛出，service 层据此走 stopped 收尾路径"""


_EVENTS: dict[str, threading.Event] = {}
_LOCK = threading.Lock()

# stop 端点先于执行线程 register 到达时（任务 pending / 极短启动窗口），
# 先记录取消意图，register 时兑现，否则令牌会被全新 event 覆盖、取消静默丢失。
# ponytail: 意图条目只在 register 兑现时清除；task_id 是 UUID 不复用，残留量
# 等于「对未开跑任务点 stop 却从未开跑」的次数，可忽略。
_CANCELLED_BEFORE_RUN: set[str] = set()


def register(task_id: object) -> threading.Event:
    """任务开跑时注册令牌（覆盖旧条目；若 stop 已先到达，返回已置位令牌）"""
    key = str(task_id)
    event = threading.Event()
    with _LOCK:
        if key in _CANCELLED_BEFORE_RUN:
            _CANCELLED_BEFORE_RUN.discard(key)
            event.set()
        _EVENTS[key] = event
    return event


def cancel(task_id: object) -> bool:
    """置位停止令牌；任务尚未注册时记录取消意图并返回 False"""
    key = str(task_id)
    with _LOCK:
        event = _EVENTS.get(key)
        if event is None:
            _CANCELLED_BEFORE_RUN.add(key)
            return False
    event.set()
    return True


def pop(task_id: object) -> None:
    """任务结束（完成/失败/终止）后移除注册表条目，防止泄漏"""
    with _LOCK:
        _EVENTS.pop(str(task_id), None)
