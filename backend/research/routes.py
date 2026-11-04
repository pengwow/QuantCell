"""研究会话 API（PRD §8，P0 子集）。

路由只做鉴权、参数校验、错误映射与任务提交；执行细节在 loop.py，
业务状态读写统一走 service.py。
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from common.schemas import ApiResponse
from factor.engine import FactorExpressionError
from factor.job_manager import job_manager
from research import consts, service
from research.job import make_runner, research_job_manager
from research.scenario import get_scenario
from research.schemas import ResearchCreateReq, ResearchExtendReq
from utils.auth import get_current_user
from utils.db_session import get_db_session
from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)

# 前缀保持相对：main.py 挂载时传 prefix="/api/v1"，最终路径为 /api/v1/research/*
router = APIRouter(prefix="/research", tags=["research"])


def _owner(current_user: dict) -> str:
    return current_user.get("user_id") or current_user.get("user_name") or "anonymous"


def _resolve_llm(model_id: str | None) -> dict[str, Any] | None:
    """复用主路由的默认模型解析（延迟导入避免 factor.routes ↔ research 循环）。"""
    from factor.routes import _resolve_llm_config

    return _resolve_llm_config(model_id)


def _http_error(exc: service.ResearchError) -> HTTPException:
    status = {"not_found": 404, "bad_state": 409, "too_many": 429, "over_budget": 422}.get(exc.kind, 400)
    return HTTPException(status_code=status, detail=exc.message)


def _manager_for(mode: str):
    """quick 复用现有 factor 池；deep 用独立研究池（PRD §9）。"""
    return job_manager if mode == "quick" else research_job_manager


def _detail(db, row) -> dict[str, Any]:
    best = service.best_trial_for(db, row)
    return service.session_to_dict(row, best_trial=best)


def _ensure_status(row, allowed: set[str], action: str) -> None:
    if row.status not in allowed:
        raise service.ResearchError("bad_state", f"会话当前状态为 {row.status}，不能执行{action}")


def _ensure_no_active_job(row: Any) -> None:
    """resume/extend 前确认旧作业线程已真正退出，避免两个线程写同一会话。"""
    if not row.backend_job_id:
        return
    status = _manager_for(row.mode).get_status(row.backend_job_id)
    if status and status.get("status") in {"pending", "running"}:
        raise service.ResearchError("bad_state", "上一个作业仍在退出中，请稍后重试继续/延期操作")


def _start_job(*, session_id: int, mode: str, cfg: dict[str, Any], llm_cfg: dict[str, Any]):
    """提交 runner 并返回 job_id；提交失败时把会话标 failed。"""
    control = service.register_control(session_id)
    runner = make_runner(session_id=session_id, mode=mode, cfg=cfg, llm_cfg=llm_cfg, control=control)

    def on_terminal(job_id: str, ok: bool, payload: Any) -> None:
        # 控制面按 job_id 归属：旧作业退出不能清掉新作业的 control
        service.clear_control(session_id, job_id)
        if ok:
            return
        # runner 在建 backend 阶段就失败时 loop 还没接手，这里兜底标 failed；
        # 只有“当前作业”才允许改会话状态，旧作业不得把新 run 标 failed
        try:
            with get_db_session() as db:
                row = service.get_session_row(db, session_id)
                if row.backend_job_id != job_id:
                    return
                if row.status in {"pending", "running"}:
                    service.set_session_status(db, row, "failed", error=str(payload))
        except Exception:
            logger.exception(f"[研究] 会话 {session_id} 收尾失败")

    manager = _manager_for(mode)
    try:
        job_id = manager.submit(
            f"research_{mode}",
            {"session_id": session_id},
            runner,
            on_terminal=on_terminal,
            # 过程事件写进 job_manager 的有界内存缓冲，供 GET /events 增量拉取
            on_event_cb=manager.append_event,
        )
        service.bind_control(session_id, job_id)
    except Exception:
        service.clear_control(session_id, None)
        with get_db_session() as db:
            row = service.get_session_row(db, session_id)
            if row.status in {"pending", "running"}:
                service.set_session_status(db, row, "failed", error="任务提交失败")
        raise
    return job_id


@router.post("/sessions", response_model=ApiResponse, summary="新建研究会话")
def create_session(
    payload: ResearchCreateReq,
    current_user: dict = Depends(get_current_user),
) -> ApiResponse:
    owner = _owner(current_user)
    # P0.5 只有 factor 场景实现；其余显式 400，禁止静默降级成 factor
    if payload.scenario != "factor":
        raise HTTPException(
            status_code=400,
            detail={
                "code": "scenario_not_supported",
                "message": f"场景 {payload.scenario} 尚未实现（当前仅支持 factor）",
            },
        )
    llm_cfg = _resolve_llm(payload.model_id)
    if llm_cfg is None:
        # 409 而非 400：请求参数本身合法，缺的是"可用模型"这一系统前置条件，
        # 前端据此引导去设置页配置，而不是当成用户填错参数
        raise HTTPException(
            status_code=409,
            detail={
                "code": "llm_unavailable",
                "message": "未配置可用的 AI 模型或 API Key，无法启动研究。请先在模型管理中配置默认模型。",
            },
        )
    cfg = payload.to_config()
    cfg["model_name"] = llm_cfg.get("model") or ""
    try:
        with get_db_session() as db:
            row = service.create_session(
                db,
                owner_id=owner,
                name=payload.name,
                mode=payload.mode,
                scenario=payload.scenario,
                config=cfg,
                n_candidates=int(payload.n_candidates or 1),
            )
            session_id = row.id
            # 先进入 running 再提交，避免 worker 极快失败时产生非法迁移
            service.set_session_status(db, row, "running")
    except service.ResearchError as exc:
        raise _http_error(exc) from exc

    job_id = _start_job(session_id=session_id, mode=payload.mode, cfg=cfg, llm_cfg=llm_cfg)
    with get_db_session() as db:
        service.update_session_fields(db, session_id, backend_job_id=job_id)
    logger.info(f"[研究] 创建会话 {session_id} mode={payload.mode} job={job_id}")
    return ApiResponse(code=0, message="ok", data={"session_id": session_id, "job_id": job_id})


@router.get("/sessions", response_model=ApiResponse, summary="研究会话列表")
def list_sessions(
    mode: str | None = Query(default=None, description="quick/deep"),
    status: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: dict = Depends(get_current_user),
) -> ApiResponse:
    with get_db_session() as db:
        total, rows = service.list_sessions(
            db,
            owner_id=_owner(current_user),
            mode=mode,
            status=status,
            limit=limit,
            offset=offset,
        )
        sessions = []
        for row in rows:
            best = service.best_trial_for(db, row)
            sessions.append(service.session_to_dict(row, best_trial=best))
    return ApiResponse(code=0, message="ok", data={"total": total, "sessions": sessions})


@router.get("/sessions/{session_id}", response_model=ApiResponse, summary="会话详情（含 trial 流）")
def get_session(
    session_id: int,
    current_user: dict = Depends(get_current_user),
) -> ApiResponse:
    with get_db_session() as db:
        try:
            row = service.get_session_row(db, session_id, _owner(current_user))
        except service.ResearchError as exc:
            raise _http_error(exc) from exc
        trials = service.list_trials(db, session_id)
        best = service.best_trial_for(db, row)
        data = service.session_to_dict(row, best_trial=best, trials=trials, include_trials=True)
    return ApiResponse(code=0, message="ok", data=data)


@router.get("/sessions/{session_id}/trials", response_model=ApiResponse, summary="会话 trial 列表")
def list_trials(
    session_id: int,
    include_code: bool = Query(default=False),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    current_user: dict = Depends(get_current_user),
) -> ApiResponse:
    with get_db_session() as db:
        try:
            service.get_session_row(db, session_id, _owner(current_user))
        except service.ResearchError as exc:
            raise _http_error(exc) from exc
        rows = service.list_trials(db, session_id, limit=limit, offset=offset)
        return ApiResponse(
            code=0,
            message="ok",
            data={"trials": [service.trial_to_dict(r, include_code=include_code) for r in rows]},
        )


@router.get(
    "/sessions/{session_id}/trials/{trial_id}",
    response_model=ApiResponse,
    summary="单条 trial 详情（含代码）",
)
def get_trial(
    session_id: int,
    trial_id: int,
    current_user: dict = Depends(get_current_user),
) -> ApiResponse:
    with get_db_session() as db:
        try:
            service.get_session_row(db, session_id, _owner(current_user))
            row = service.get_trial_row(db, trial_id)
        except service.ResearchError as exc:
            raise _http_error(exc) from exc
        if row.session_id != session_id:
            raise HTTPException(status_code=404, detail="trial 不属于该会话")
        return ApiResponse(code=0, message="ok", data=service.trial_to_dict(row))


@router.post(
    "/sessions/{session_id}/trials/{trial_id}/promote",
    response_model=ApiResponse,
    summary="采纳 trial 为因子",
    description="把 trial 代码写入因子库；幂等，重复采纳返回既有因子名。",
)
def promote_trial(
    session_id: int,
    trial_id: int,
    current_user: dict = Depends(get_current_user),
) -> ApiResponse:
    with get_db_session() as db:
        try:
            row = service.get_session_row(db, session_id, _owner(current_user))
            trial = service.get_trial_row(db, trial_id)
        except service.ResearchError as exc:
            raise _http_error(exc) from exc
        if trial.session_id != session_id:
            raise HTTPException(status_code=404, detail="trial 不属于该会话")
        payload = service.trial_to_dict(trial)
        # 会话归属/场景从 config_json 读：ResearchSession 没有 config 属性
        scenario_name = str(service.session_config(row).get("scenario") or "factor")

    try:
        scenario = get_scenario(scenario_name)
    except LookupError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "scenario_not_supported", "message": str(exc)},
        ) from exc
    try:
        factor_name = scenario.promote(payload)
    except (ValueError, FactorExpressionError) as exc:
        # 幂等/校验失败都按 400 返回，前端提示即可，不重试
        raise HTTPException(status_code=400, detail={"code": "promote_rejected", "message": str(exc)}) from exc
    return ApiResponse(code=0, message="ok", data={"factor_name": factor_name})


@router.get("/sessions/{session_id}/events", response_model=ApiResponse, summary="会话事件流")
def get_events(
    session_id: int,
    after_seq: int = Query(default=0, ge=0, description="只返回 seq 大于该值的事件"),
    current_user: dict = Depends(get_current_user),
) -> ApiResponse:
    with get_db_session() as db:
        try:
            service.get_session_row(db, session_id, _owner(current_user))
        except service.ResearchError as exc:
            raise _http_error(exc) from exc
        # 事件从 research_events 持久化表增量读取：不再依赖持有 job 的进程内存缓冲，
        # 多 worker 部署下任一进程都能看到进度；局限见 models.ResearchEvent 注释
        data = service.list_events(db, session_id, after_seq)
    return ApiResponse(code=0, message="ok", data=data)


@router.post("/sessions/{session_id}/pause", response_model=ApiResponse, summary="暂停会话")
def pause_session(
    session_id: int,
    current_user: dict = Depends(get_current_user),
) -> ApiResponse:
    with get_db_session() as db:
        try:
            row = service.get_session_row(db, session_id, _owner(current_user))
            _ensure_status(row, {"running"}, "暂停")
            # quick 是一次性批量调用，没有 step 边界可停；明确拒绝，避免“点了暂停实际还在跑”
            if row.mode == "quick":
                raise HTTPException(
                    status_code=409,
                    detail={"code": "pause_unsupported", "message": "quick 会话不支持暂停，请取消后重跑"},
                )
            service.set_session_status(db, row, "paused")
            data = _detail(db, row)
        except service.ResearchError as exc:
            raise _http_error(exc) from exc
    ctrl = service.get_control(session_id)
    if ctrl is not None:
        ctrl.pause.set()
    return ApiResponse(code=0, message="ok", data=data)


@router.post("/sessions/{session_id}/resume", response_model=ApiResponse, summary="继续会话")
def resume_session(
    session_id: int,
    current_user: dict = Depends(get_current_user),
) -> ApiResponse:
    with get_db_session() as db:
        try:
            row = service.get_session_row(db, session_id, _owner(current_user))
            _ensure_status(row, {"paused"}, "继续")
            _ensure_no_active_job(row)
            # 在会话关闭前取出 cfg/mode，避免 ORM 属性过期后访问报 DetachedInstanceError
            cfg = service.session_config(row)
            mode = row.mode
            llm_cfg = _resolve_llm(cfg.get("model_id"))
            if llm_cfg is None:
                raise service.ResearchError("invalid", "未配置可用的默认 AI 模型或 API Key，请先在模型管理中配置")
            service.set_session_status(db, row, "running")
        except service.ResearchError as exc:
            raise _http_error(exc) from exc
    job_id = _start_job(session_id=session_id, mode=mode, cfg=cfg, llm_cfg=llm_cfg)
    with get_db_session() as db:
        service.update_session_fields(db, session_id, backend_job_id=job_id)
    return ApiResponse(code=0, message="ok", data={"session_id": session_id, "job_id": job_id})


@router.post("/sessions/{session_id}/cancel", response_model=ApiResponse, summary="取消会话")
def cancel_session(
    session_id: int,
    current_user: dict = Depends(get_current_user),
) -> ApiResponse:
    with get_db_session() as db:
        try:
            row = service.get_session_row(db, session_id, _owner(current_user))
            _ensure_status(row, {"pending", "running", "paused"}, "取消")
            service.set_session_status(db, row, "cancelled")
            data = _detail(db, row)
        except service.ResearchError as exc:
            raise _http_error(exc) from exc
    ctrl = service.get_control(session_id)
    if ctrl is not None:
        ctrl.cancel.set()
    return ApiResponse(code=0, message="ok", data=data)


@router.post("/sessions/{session_id}/extend", response_model=ApiResponse, summary="继续研究")
def extend_session(
    session_id: int,
    payload: ResearchExtendReq,
    current_user: dict = Depends(get_current_user),
) -> ApiResponse:
    with get_db_session() as db:
        try:
            row = service.get_session_row(db, session_id, _owner(current_user))
            _ensure_status(row, {"completed"}, "继续研究")
            _ensure_no_active_job(row)
            mode = row.mode
            cfg = service.session_config(row)
            base_loops = int(cfg.get("loop_n") or 1)
            new_loops = base_loops + payload.extra_loops
            if new_loops > consts.MAX_LOOP_N:
                raise service.ResearchError(
                    "bad_state",
                    f"累计轮次不能超过 {consts.MAX_LOOP_N}（当前 {base_loops}，追加后 {new_loops}）",
                )
            cfg["loop_n"] = new_loops
            # 预算按剩余额度续算：旧上限 + 新增额度，运行期从已用值继续扣
            cfg["max_llm_calls"] = int(cfg.get("max_llm_calls") or 0) + payload.extra_max_llm_calls
            cfg["max_tokens"] = int(cfg.get("max_tokens") or 0) + payload.extra_max_tokens
            if mode == "quick":
                # quick 会话 extend：保留原 mode（不改写，列表/筛选口径不变），
                # 仅记 extended_at；追加轮次改走 deep 编排，并从 quick 轮最佳候选作为 SOTA 继续
                cfg["extend_deep"] = True
                if row.best_trial_id is None:
                    best = service.best_evaluated_trial(db, session_id)
                    if best is not None:
                        service.update_session_fields(db, session_id, best_trial_id=best.id)
            llm_cfg = _resolve_llm(cfg.get("model_id"))
            if llm_cfg is None:
                raise service.ResearchError("invalid", "未配置可用的默认 AI 模型或 API Key，请先在模型管理中配置")
            service.set_session_status(db, row, "running")
            service.update_session_fields(
                db,
                session_id,
                config_json=json.dumps(cfg, ensure_ascii=False),
                extended_at=datetime.now(),
                error=None,
            )
        except service.ResearchError as exc:
            raise _http_error(exc) from exc
    job_id = _start_job(session_id=session_id, mode=mode, cfg=cfg, llm_cfg=llm_cfg)
    with get_db_session() as db:
        service.update_session_fields(db, session_id, backend_job_id=job_id)
    return ApiResponse(code=0, message="ok", data={"session_id": session_id, "job_id": job_id})
