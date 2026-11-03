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


# 终止确认：stop 端点投递令牌后同步等执行线程退出（限时），据此向用户反馈
# 「终止成功」还是「超时已强制终止」，不再让按钮点下去后石沉大海
_EXIT_SIGNALS: dict[str, threading.Event] = {}


def notify_exit(task_id: object) -> None:
    """执行线程退出 run_backtest 时调用（无论结果），唤醒等待终止确认的 stop 端点"""
    with _LOCK:
        event = _EXIT_SIGNALS.get(str(task_id))
    if event:
        event.set()


def cancel_and_wait(task_id: object, timeout: float) -> bool:
    """stop 端点专用：置位取消令牌并等待执行线程退出确认。

    返回 True = 线程已退出（终止达成）；False = 超时。daemon 线程无法被安全
    强杀（见文件头注释），超时的「强制终止」语义 = 任务记录已由 stop 端点置为
    stopped + 令牌已置位，引擎将在下一品种边界/收尾点自动退出，其后续结果
    写入被竞态防护挡住。

    ponytail: 执行线程恰好在「stop 端点读状态之后、注册等待器之前」退出的
    极小窗口会误报超时；后果只是提示措辞，任务状态终归 stopped，不专门处理。
    """
    key = str(task_id)
    event = threading.Event()
    with _LOCK:
        # 先注册等待器再置位令牌，消除 notify_exit 插在两步之间导致的漏报
        _EXIT_SIGNALS[key] = event
    cancel(task_id)
    try:
        return event.wait(timeout)
    finally:
        with _LOCK:
            # 只清自己的等待器，避免误删并发请求注册的同名条目
            if _EXIT_SIGNALS.get(key) is event:
                _EXIT_SIGNALS.pop(key, None)
