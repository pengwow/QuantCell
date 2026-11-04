"""研究会话持久化与序列化。

分层约定：本模块只管 DB 读写与状态校验；路由只做参数校验/鉴权/错误映射，
线程只负责编排（loop.py）。
"""

from __future__ import annotations

import json
import threading
from typing import Any

from sqlalchemy import func, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from research.consts import MAX_ACTIVE_SESSIONS
from research.models import ResearchSession, ResearchTrial
from research.state import InvalidTransition, ensure_session_transition, ensure_trial_transition
from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)


class ResearchError(Exception):
    """研究模块业务错误，kind 供路由映射 HTTP 状态码。"""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind
        self.message = message


def _loads(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except TypeError, ValueError:
        return default


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


# ---------- 控制面（暂停/取消）----------


class Control:
    """每个运行中会话一个控制对象，线程在每个 step 边界检查。

    job_id 由路由 submit 后回填：只有当前作业能清理/操作这个控制对象，
    避免旧线程退出时误删新作业的 control。
    """

    def __init__(self) -> None:
        self.cancel = threading.Event()
        self.pause = threading.Event()
        self.job_id: str | None = None


_controls: dict[int, Control] = {}
_controls_lock = threading.Lock()


def register_control(session_id: int) -> Control:
    with _controls_lock:
        ctrl = Control()
        _controls[session_id] = ctrl
        return ctrl


def bind_control(session_id: int, job_id: str) -> None:
    """submit 返回 job_id 后回填归属。"""
    with _controls_lock:
        ctrl = _controls.get(session_id)
        if ctrl is not None:
            ctrl.job_id = job_id


def get_control(session_id: int) -> Control | None:
    with _controls_lock:
        return _controls.get(session_id)


def clear_control(session_id: int, job_id: str | None) -> None:
    """只在 job_id 匹配（或尚未绑定）时清理，避免旧作业误删新作业的控制面。"""
    with _controls_lock:
        ctrl = _controls.get(session_id)
        if ctrl is None:
            return
        if job_id is not None and ctrl.job_id is not None and ctrl.job_id != job_id:
            return
        _controls.pop(session_id, None)


# ---------- 会话 ----------


def create_session(
    db: Session,
    *,
    owner_id: str,
    name: str,
    mode: str,
    scenario: str,
    config: dict[str, Any],
    n_candidates: int,
    request_id: str | None = None,
) -> ResearchSession:
    active = (
        db.query(func.count(ResearchSession.id))
        .filter(
            ResearchSession.owner_id == owner_id,
            ResearchSession.status.in_(["pending", "running"]),
        )
        .scalar()
        or 0
    )
    if active >= MAX_ACTIVE_SESSIONS:
        raise ResearchError("too_many", f"同时运行的研究会话不能超过 {MAX_ACTIVE_SESSIONS} 个，请先等待或取消")
    row = ResearchSession(
        owner_id=owner_id,
        name=name,
        status="pending",
        scenario=scenario,
        mode=mode,
        n_candidates=n_candidates,
        config_json=_dumps(config),
        request_id=request_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_session_row(db: Session, session_id: int, owner_id: str | None = None) -> ResearchSession:
    row = db.get(ResearchSession, session_id)
    if row is None or (owner_id is not None and row.owner_id != owner_id):
        raise ResearchError("not_found", f"研究会话 {session_id} 不存在")
    return row


def list_sessions(
    db: Session,
    *,
    owner_id: str,
    mode: str | None,
    status: str | None,
    limit: int,
    offset: int,
) -> tuple[int, list[ResearchSession]]:
    q = db.query(ResearchSession).filter(ResearchSession.owner_id == owner_id)
    if mode:
        q = q.filter(ResearchSession.mode == mode)
    if status:
        q = q.filter(ResearchSession.status == status)
    total = q.count()
    rows = q.order_by(ResearchSession.created_at.desc()).offset(offset).limit(limit).all()
    return total, rows


def set_session_status(db: Session, row: ResearchSession, target: str, *, error: str | None = None) -> None:
    """CAS 更新会话状态：`WHERE status = 读到的旧值`，rowcount=0 → 409。

    读-校验-写之间可能被其它线程改状态（pause/cancel/extend/旧作业收尾），
    CAS 让并发下的状态迁移保持单赢家，调用方拿不到锁就不要硬写。
    """
    expected = row.status
    try:
        ensure_session_transition(expected, target)
    except InvalidTransition as exc:
        raise ResearchError("bad_state", str(exc)) from exc

    values: dict[str, Any] = {"status": target}
    if error is not None:
        values["error"] = error[:2000]
    result = db.execute(
        update(ResearchSession).where(ResearchSession.id == row.id, ResearchSession.status == expected).values(**values)
    )
    db.commit()
    if result.rowcount == 0:
        # 被并发改状态：调用方需要按最新状态决定下一步，而不是覆盖
        db.refresh(row)
        raise ResearchError("bad_state", f"会话状态已变更（期望 {expected}），当前为 {row.status}，请刷新后重试")
    db.refresh(row)


def update_session_fields(db: Session, session_id: int, **fields: Any) -> None:
    """无条件更新非状态字段（成本、进度、最佳 trial 等）。"""
    row = db.get(ResearchSession, session_id)
    if row is None:
        raise ResearchError("not_found", f"研究会话 {session_id} 不存在")
    for key, value in fields.items():
        setattr(row, key, value)
    db.commit()


def session_config(row: ResearchSession) -> dict[str, Any]:
    return _loads(row.config_json, {})


# ---------- 试验 ----------


def add_trial(db: Session, session_id: int, fields: dict[str, Any]) -> ResearchTrial:
    payload: dict[str, Any] = {}
    for key in (
        "metrics_json",
        "metrics_oos_json",
        "feedback_json",
        "judge_json",
        "task_json",
    ):
        value = fields.get(key)
        payload[key] = _dumps(value) if isinstance(value, (dict, list)) else value
    for key in (
        "loop_idx",
        "candidate_idx",
        "status",
        "hypothesis",
        "hypothesis_reason",
        "hypothesis_prediction",
        "code",
        "code_hash",
        "oos_flag",
        "oos_note",
        "decision",
        "corr_sota",
        "corr_library",
        "quick_run_id",
        "parent_trial_id",
        "replay_of_id",
        "exception",
        "token_used",
        "llm_calls",
        "model",
        "prompt_hash",
        "temperature",
        "duration_ms",
    ):
        if key in fields:
            payload[key] = fields[key]
    row = ResearchTrial(session_id=session_id, **payload)
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ResearchError(
            "duplicate_trial",
            f"会话 {session_id} 的 loop/candidate 已存在 trial（不应重复落库）",
        ) from exc
    db.refresh(row)
    return row


def get_or_add_trial(db: Session, session_id: int, fields: dict[str, Any]) -> tuple[ResearchTrial, bool]:
    """按唯一键取或建 trial，返回 (行, 是否新建)。

    并发/重试场景下同 (session, loop_idx, candidate_idx) 可能被建两次，
    唯一索引会拦第二条；这里把 IntegrityError 转成"复用已有行"，
    避免整个研究循环因为一次撞键直接失败。
    """
    try:
        return add_trial(db, session_id, fields), True
    except ResearchError as exc:
        if exc.kind != "duplicate_trial":
            raise
        rows = db.query(ResearchTrial).filter(ResearchTrial.session_id == session_id).all()
        row = next(
            (
                r
                for r in rows
                if r.loop_idx == int(fields.get("loop_idx", 1))
                and r.candidate_idx == int(fields.get("candidate_idx", 1))
            ),
            None,
        )
        if row is None:
            raise
        return row, False


def get_trial_row(db: Session, trial_id: int) -> ResearchTrial:
    row = db.get(ResearchTrial, trial_id)
    if row is None:
        raise ResearchError("not_found", f"试验 {trial_id} 不存在")
    return row


def update_trial(db: Session, trial_id: int, *, status: str | None = None, **fields: Any) -> ResearchTrial:
    row = get_trial_row(db, trial_id)
    if status is not None and status != row.status:
        ensure_trial_transition(row.status, status)
        row.status = status
    for key, value in fields.items():
        if key.endswith("_json") and isinstance(value, (dict, list)):
            value = _dumps(value)
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return row


def list_trials(db: Session, session_id: int, limit: int = 500, offset: int = 0) -> list[ResearchTrial]:
    return (
        db.query(ResearchTrial)
        .filter(ResearchTrial.session_id == session_id)
        .order_by(ResearchTrial.loop_idx, ResearchTrial.candidate_idx, ResearchTrial.id)
        .offset(offset)
        .limit(limit)
        .all()
    )


# trial 的终态：这些状态不再参与续跑
TERMINAL_TRIAL_STATUSES = frozenset({"judged", "failed"})


def find_trial(db: Session, session_id: int, loop_idx: int, candidate_idx: int = 1) -> ResearchTrial | None:
    return (
        db.query(ResearchTrial)
        .filter(
            ResearchTrial.session_id == session_id,
            ResearchTrial.loop_idx == loop_idx,
            ResearchTrial.candidate_idx == candidate_idx,
        )
        .one_or_none()
    )


# ---------- 序列化 ----------


def trial_to_dict(row: ResearchTrial, *, include_code: bool = True) -> dict[str, Any]:
    data = {
        "id": row.id,
        # promote 需要会话归属做 provenance，序列化时一并给出
        "session_id": row.session_id,
        "loop_idx": row.loop_idx,
        "candidate_idx": row.candidate_idx,
        "status": row.status,
        "resume_status": row.resume_status,
        "hypothesis": row.hypothesis,
        "hypothesis_reason": row.hypothesis_reason,
        "hypothesis_prediction": row.hypothesis_prediction,
        "task": _loads(row.task_json, None),
        "code_hash": row.code_hash,
        "metrics": _loads(row.metrics_json, {}),
        "metrics_oos": _loads(row.metrics_oos_json, {}),
        "oos_flag": row.oos_flag,
        "oos_note": row.oos_note,
        "feedback": _loads(row.feedback_json, None),
        "repair": _loads(row.repair_json, None),
        "judge": _loads(row.judge_json, None),
        "decision": row.decision,
        "corr_sota": row.corr_sota,
        "corr_library": row.corr_library,
        "promoted_factor_name": row.promoted_factor_name,
        "quick_run_id": row.quick_run_id,
        "parent_trial_id": row.parent_trial_id,
        "replay_of_id": row.replay_of_id,
        "token_used": row.token_used,
        "llm_calls": row.llm_calls,
        "model": row.model,
        "prompt_hash": row.prompt_hash,
        "temperature": row.temperature,
        "duration_ms": row.duration_ms,
        "exception": row.exception,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
    if include_code:
        data["code"] = row.code
    return data


def session_to_dict(
    row: ResearchSession,
    *,
    best_trial: ResearchTrial | None = None,
    trials: list[ResearchTrial] | None = None,
    include_trials: bool = False,
) -> dict[str, Any]:
    config = session_config(row)
    loop_n = int(config.get("loop_n") or 1)
    best_metrics = _loads(best_trial.metrics_json, {}) if best_trial else {}
    data = {
        "id": row.id,
        "name": row.name,
        "mode": row.mode,
        "scenario": row.scenario,
        "status": row.status,
        "n_candidates": row.n_candidates,
        "loop_n": loop_n,
        "loop_done": row.loop_done,
        "step_idx": row.step_idx,
        "token_used": row.token_used,
        "llm_calls": row.llm_calls,
        "max_tokens": config.get("max_tokens"),
        "max_llm_calls": config.get("max_llm_calls"),
        "best_trial_id": row.best_trial_id,
        "best_ic_ir": best_metrics.get("ic_ir"),
        "error": row.error,
        "config": config,
        "backend_job_id": row.backend_job_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "extended_at": row.extended_at.isoformat() if row.extended_at else None,
    }
    if include_trials:
        data["trials"] = [trial_to_dict(t, include_code=False) for t in (trials or [])]
    return data


def best_trial_for(db: Session, row: ResearchSession) -> ResearchTrial | None:
    if row.best_trial_id is None:
        return None
    return db.get(ResearchTrial, row.best_trial_id)
