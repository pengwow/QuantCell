"""会话/试验状态机。

数据库里 status 存字符串，写入前必须经过这里校验，避免路由或线程把非法迁移
（例如 cancelled → running）静默写进 DB。
"""

from __future__ import annotations

from enum import StrEnum


class InvalidTransition(ValueError):
    """非法的状态迁移。"""


class SessionStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TrialStatus(StrEnum):
    PLANNED = "planned"
    CODING = "coding"
    CODED = "coded"
    RUNNING = "running"
    EVALUATED = "evaluated"
    JUDGED = "judged"
    FAILED = "failed"


SESSION_TRANSITIONS: dict[str, frozenset[str]] = {
    SessionStatus.PENDING: frozenset({SessionStatus.RUNNING, SessionStatus.CANCELLED, SessionStatus.FAILED}),
    SessionStatus.RUNNING: frozenset(
        {
            SessionStatus.PAUSED,
            SessionStatus.COMPLETED,
            SessionStatus.FAILED,
            SessionStatus.CANCELLED,
        }
    ),
    # paused → completed：暂停后剩余工作已跑完 / 暂停请求晚到的正常收尾
    SessionStatus.PAUSED: frozenset({SessionStatus.RUNNING, SessionStatus.COMPLETED, SessionStatus.CANCELLED}),
    # completed 允许继续研究（extend）重新进入 running
    SessionStatus.COMPLETED: frozenset({SessionStatus.RUNNING}),
    SessionStatus.FAILED: frozenset({SessionStatus.CANCELLED}),
    SessionStatus.CANCELLED: frozenset(),
}

TRIAL_TRANSITIONS: dict[str, frozenset[str]] = {
    TrialStatus.PLANNED: frozenset({TrialStatus.CODING, TrialStatus.FAILED}),
    TrialStatus.CODING: frozenset({TrialStatus.CODED, TrialStatus.FAILED}),
    TrialStatus.CODED: frozenset({TrialStatus.RUNNING, TrialStatus.FAILED}),
    TrialStatus.RUNNING: frozenset({TrialStatus.EVALUATED, TrialStatus.FAILED}),
    TrialStatus.EVALUATED: frozenset({TrialStatus.JUDGED, TrialStatus.FAILED}),
    TrialStatus.JUDGED: frozenset(),
    TrialStatus.FAILED: frozenset(),
}


def ensure_session_transition(current: str, target: str) -> None:
    """校验会话状态迁移，非法时抛 InvalidTransition。"""
    if target not in SESSION_TRANSITIONS.get(current, frozenset()):
        raise InvalidTransition(f"session 不允许从 {current} 迁移到 {target}")


def ensure_trial_transition(current: str, target: str) -> None:
    """校验试验状态迁移，非法时抛 InvalidTransition。"""
    if target not in TRIAL_TRANSITIONS.get(current, frozenset()):
        raise InvalidTransition(f"trial 不允许从 {current} 迁移到 {target}")
