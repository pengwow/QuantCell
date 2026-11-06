"""研究会话持久化与序列化。

分层约定：本模块只管 DB 读写与状态校验；路由只做参数校验/鉴权/错误映射，
线程只负责编排（loop.py）。
"""

from __future__ import annotations

import json
import re
import threading
import time
from typing import Any

from sqlalchemy import func, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from research import consts
from research.models import ResearchEvent, ResearchKnowledge, ResearchSession, ResearchTrial
from research.state import InvalidTransition, ensure_session_transition, ensure_trial_transition
from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)


class ResearchError(Exception):
    """研究模块业务错误，kind 供路由映射 HTTP 状态码。"""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind
        self.message = message


# 控制字符（C0 除 \n\t\r、DEL、C1）会破坏 JSON 序列化/响应：
# LLM 输出偶尔带 \x00-\x1f 原始字节，写库前与读库/序列化时都清洗一次。
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


def sanitize_text(value: str) -> str:
    """去掉会破坏 JSON 的控制字符，保留换行/制表符。"""
    return _CONTROL_CHARS.sub("", value)


def sanitize_value(value: Any) -> Any:
    """递归清洗 dict/list 中的字符串（JSON 字段落库前使用）。"""
    if isinstance(value, str):
        return sanitize_text(value)
    if isinstance(value, dict):
        return {sanitize_text(str(k)): sanitize_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize_value(v) for v in value]
    return value


def _loads(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        # 历史行可能已落库了原始控制字符，先清洗再解析，避免整个接口 500
        return json.loads(_CONTROL_CHARS.sub("", raw))
    except TypeError, ValueError:
        return default


def _dumps(value: Any) -> str:
    return json.dumps(sanitize_value(value), ensure_ascii=False, default=str)


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


def estimate_budget(mode: str, config: dict[str, Any], n_candidates: int) -> tuple[int, int]:
    """按候选数/轮次粗估会话消耗 (calls, tokens)。

    该值只用于创建/详情的**提示**（session_to_dict 的 budget_hint），不作为创建拦截
    条件：真实单次消耗常远低于 EST_TOKENS_PER_CALL，按估算硬拒会逼用户抬高上限、
    再靠运行期监控去取消，反而多花钱。运行期仍由 Budget 的预留/结算兜底。
    """
    loops = max(int(config.get("loop_n") or 1), 1)
    if mode == "quick":
        calls = max(int(n_candidates), 1) * consts.QUICK_CALLS_PER_CANDIDATE + consts.QUICK_EXTRA_CALLS
    else:
        calls = loops * (consts.DEEP_CALLS_PER_LOOP + int(config.get("repair_rounds") or 0))
    return calls, calls * consts.EST_TOKENS_PER_CALL


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
    if active >= consts.MAX_ACTIVE_SESSIONS:
        raise ResearchError("too_many", f"同时运行的研究会话不能超过 {consts.MAX_ACTIVE_SESSIONS} 个，请先等待或取消")

    # 预算估算只用于提示，不拦截创建：额度是否够由运行期 Budget 预留/结算决定。
    # 硬校验留在 schema 边界（max_tokens >= 单次预留下限、max_llm_calls >= 1），
    # 这样 60k + loop_n=2 这类“低于估算但实际够用”的配置可以正常创建。
    est_calls, est_tokens = estimate_budget(mode, config, n_candidates)
    logger.info(
        f"[研究] 创建预算提示 calls≈{est_calls} tokens≈{est_tokens} "
        f"上限 calls={config.get('max_llm_calls')} tokens={config.get('max_tokens')}"
    )

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
        "replay_meta_json",
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


def get_trials_for_session(db: Session, session_id: int, trial_ids: list[int]) -> list[ResearchTrial]:
    """批量取 trial（对比用），保持请求顺序；有不属于本会话的 id 直接 404。"""
    rows = db.query(ResearchTrial).filter(ResearchTrial.session_id == session_id, ResearchTrial.id.in_(trial_ids)).all()
    found = {row.id: row for row in rows}
    missing = [tid for tid in trial_ids if tid not in found]
    if missing:
        # 跨会话混选同样视为“不存在”，避免泄露其他会话的 trial
        raise ResearchError("not_found", f"试验 {missing} 不属于会话 {session_id}")
    return [found[tid] for tid in trial_ids]


# trial 的终态：这些状态不再参与续跑（duplicate 判重消耗、skipped 知识短路消耗）
TERMINAL_TRIAL_STATUSES = frozenset({"judged", "failed", "duplicate", "skipped"})


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


def best_evaluated_trial(db: Session, session_id: int, metric: str = "ic_ir") -> ResearchTrial | None:
    """quick 轮的最佳候选（按指标取最大），供 extend 后作为 SOTA 继续。"""
    rows = (
        db.query(ResearchTrial)
        .filter(
            ResearchTrial.session_id == session_id,
            ResearchTrial.status.in_(["evaluated", "judged"]),
        )
        .all()
    )
    best: ResearchTrial | None = None
    best_score = float("-inf")
    for row in rows:
        metrics = _loads(row.metrics_json, {})
        if not isinstance(metrics, dict) or metrics.get(metric) is None:
            continue
        try:
            score = float(metrics[metric])
        except TypeError, ValueError:
            continue
        if score > best_score:
            best, best_score = row, score
    return best


# ---------- 失败签名知识库 ----------

# 这些片段在错误信息里只是“这一次的取值”，不能参与签名，否则同一种失败会被拆成多条
_VOLATILE_PATTERNS = (
    re.compile(r"0x[0-9a-fA-F]+"),  # 内存地址
    re.compile(r"[0-9a-fA-F]{8,}"),  # 哈希/长十六进制
    re.compile(r"\d+"),  # 行号、bar 下标、耗时等数字
)


def failure_signature(kind: str, error: str) -> str:
    """失败签名 = 错误类型 + 归一化关键特征（抹掉地址/哈希/数字后截断）。

    这是启发式口径，不追求语义聚类：同类型 + 同段错误文本（忽略取值差异）
    视为同一种坑，够用来做“别重复踩同一个坑”的提示。
    """
    feature = error or ""
    for pattern in _VOLATILE_PATTERNS:
        feature = pattern.sub("#", feature)
    feature = re.sub(r"\s+", " ", feature).strip().lower()[:80]
    return f"{kind}|{feature}"


def record_failure(
    db: Session,
    *,
    owner_id: str | None,
    session_id: int | None,
    trial_id: int | None,
    kind: str,
    error: str,
    hint: str = "",
) -> ResearchKnowledge:
    """落一条失败签名；同 owner 下同签名累加 hit_count，避免重复堆行。"""
    signature = failure_signature(kind, error)
    payload = {"kind": kind, "error": (error or "")[:200], "hint": (hint or "")[:200]}
    row = (
        db.query(ResearchKnowledge)
        .filter(
            ResearchKnowledge.owner_id == owner_id,
            ResearchKnowledge.kind == "failure",
            ResearchKnowledge.signature == signature,
        )
        .order_by(ResearchKnowledge.id)
        .first()
    )
    if row is None:
        row = ResearchKnowledge(
            owner_id=owner_id,
            session_id=session_id,
            trial_id=trial_id,
            kind="failure",
            signature=signature,
            payload_json=_dumps(payload),
            hit_count=1,
        )
        db.add(row)
    else:
        row.hit_count += 1
        row.payload_json = _dumps(payload)
        row.trial_id = trial_id or row.trial_id
        row.session_id = session_id or row.session_id
    db.commit()
    db.refresh(row)
    return row


def list_failure_knowledge(db: Session, owner_id: str | None, limit: int = 5) -> list[dict[str, Any]]:
    """按命中次数取最近的失败签名，供 propose/plan 上下文注入。"""
    rows = (
        db.query(ResearchKnowledge)
        .filter(ResearchKnowledge.owner_id == owner_id, ResearchKnowledge.kind == "failure")
        .order_by(ResearchKnowledge.hit_count.desc(), ResearchKnowledge.updated_at.desc())
        .limit(limit)
        .all()
    )
    items: list[dict[str, Any]] = []
    for row in rows:
        payload = _loads(row.payload_json, {})
        if not isinstance(payload, dict):
            payload = {}
        items.append(
            {
                "signature": row.signature,
                "hit_count": row.hit_count,
                "hint": payload.get("hint") or "",
                "error": payload.get("error") or "",
            }
        )
    return items


def blocked_task_hints(db: Session, owner_id: str | None, threshold: int) -> list[str]:
    """命中次数达阈值的失败签名所对应的任务文本（hint，归一化去重），供执行前短路。

    短路口径：同一失败签名（错误类型 + 归一化错误文本）累计失败 threshold 次，
    视为该任务在重复踩同一坑；执行前再遇到相同任务描述（归一化相等）直接跳过，
    不再为它调用 LLM。hint 为空的历史失败（无任务上下文）不参与短路。
    """
    rows = (
        db.query(ResearchKnowledge)
        .filter(
            ResearchKnowledge.owner_id == owner_id,
            ResearchKnowledge.kind == "failure",
            ResearchKnowledge.hit_count >= threshold,
        )
        .all()
    )
    hints: list[str] = []
    seen: set[str] = set()
    for row in rows:
        payload = _loads(row.payload_json, {})
        if not isinstance(payload, dict):
            continue
        hint = re.sub(r"\s+", " ", str(payload.get("hint") or "")).strip().lower()
        if hint and hint not in seen:
            seen.add(hint)
            hints.append(hint)
    return hints


# ---------- 过程事件 ----------

# 多 worker 兜底：事件写库而不是留在进程内缓冲，任一进程都能增量读到同一会话的进度。
# seq = 自增主键（写库顺序），不做会话级锁/独立 seq 分配，明确接受“最终一致”；
# 决策与局限见 models.ResearchEvent 的注释（单会话单写者时 seq 与发生顺序一致）。


def append_event(db: Session, session_id: int, level: str, stage: str, msg: str) -> ResearchEvent:
    """落一条过程事件；超出保留上限时裁剪最旧的，避免事件表无限增长。"""
    row = ResearchEvent(
        session_id=session_id,
        level=level,
        stage=sanitize_text(stage),
        msg=sanitize_text(msg)[:2000],
        ts=time.time(),
    )
    db.add(row)
    db.flush()
    db.query(ResearchEvent).filter(
        ResearchEvent.session_id == session_id,
        ResearchEvent.id <= row.id - consts.EVENTS_RETENTION,
    ).delete(synchronize_session=False)
    db.commit()
    return row


def list_events(
    db: Session, session_id: int, after_seq: int = 0, limit: int = consts.EVENTS_DEFAULT_LIMIT
) -> dict[str, Any]:
    """按 seq 增量拉取事件，返回 (events, next_seq)，供前端轮询续读。"""
    rows = (
        db.query(ResearchEvent)
        .filter(ResearchEvent.session_id == session_id, ResearchEvent.id > after_seq)
        .order_by(ResearchEvent.id)
        .limit(limit)
        .all()
    )
    events = [
        {
            "seq": row.id,
            "level": row.level,
            "stage": sanitize_text(row.stage),
            "msg": sanitize_text(row.msg),
            "ts": int(row.ts or 0),
        }
        for row in rows
    ]
    next_seq = rows[-1].id if rows else after_seq
    return {"session_id": session_id, "events": events, "next_seq": next_seq}


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
        "replay_meta": _loads(row.replay_meta_json, None),
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
    # 兜底清洗：历史行/LLM 原文可能带控制字符，序列化前统一去掉，
    # 避免响应组装阶段再抛 Invalid control character
    return {key: sanitize_text(value) if isinstance(value, str) else value for key, value in data.items()}


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
    est_calls, est_tokens = estimate_budget(row.mode, config, row.n_candidates)
    max_tokens = config.get("max_tokens")
    budget_hint = None
    if max_tokens and est_tokens > int(max_tokens):
        # 只是提示：低于估算不拦截创建，运行中由 Budget 预留/结算决定是否提前收尾
        budget_hint = (
            f"按 {row.n_candidates} 个候选 / {loop_n} 轮估算约需 {est_calls} 次调用、{est_tokens} tokens，"
            f"当前上限 {max_tokens} 可能提前耗尽（仅提示，不拦截运行）"
        )
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
        "max_tokens": max_tokens,
        "max_llm_calls": config.get("max_llm_calls"),
        "estimated_calls": est_calls,
        "estimated_tokens": est_tokens,
        "budget_hint": budget_hint,
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
    return {key: sanitize_text(value) if isinstance(value, str) else value for key, value in data.items()}


def best_trial_for(db: Session, row: ResearchSession) -> ResearchTrial | None:
    if row.best_trial_id is None:
        return None
    return db.get(ResearchTrial, row.best_trial_id)


def best_trials_for(db: Session, rows: list[ResearchSession]) -> dict[int, ResearchTrial]:
    """列表页一次取齐所有 best trial，避免逐行查询的 N+1。"""
    ids = [row.best_trial_id for row in rows if row.best_trial_id is not None]
    if not ids:
        return {}
    trials = db.query(ResearchTrial).filter(ResearchTrial.id.in_(ids)).all()
    return {trial.id: trial for trial in trials}
