"""研究会话 API（PRD §8，P0 子集）。

路由只做鉴权、参数校验、错误映射与任务提交；执行细节在 loop.py，
业务状态读写统一走 service.py。
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket

from common.schemas import ApiResponse
from factor import job_lease
from factor.engine import FactorExpressionError
from factor.job_manager import job_manager
from research import consts, replay, service
from research import ws as research_ws
from research.job import make_runner, research_job_manager
from research.scenario import get_scenario
from research.scenarios.factor import load_seed_factor
from research.schemas import ResearchCreateReq, ResearchExtendReq, ResearchTrialBatchReq
from utils.auth import authenticate_request, get_current_user
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
    status = {
        "not_found": 404,
        "bad_state": 409,
        "too_many": 429,
        "over_budget": 422,
        "replay_failed": 422,
    }.get(exc.kind, 400)
    return HTTPException(status_code=status, detail=exc.message)


def _manager_for(mode: str):
    """quick 复用现有 factor 池；deep 用独立研究池（PRD §9）。"""
    return job_manager if mode == "quick" else research_job_manager


def _detail(db, row) -> dict[str, Any]:
    best = service.best_trial_for(db, row)
    return service.session_to_dict(row, db=db, best_trial=best)


def _ensure_status(row, allowed: set[str], action: str) -> None:
    if row.status not in allowed:
        raise service.ResearchError("bad_state", f"会话当前状态为 {row.status}，不能执行{action}")


def _ensure_no_active_job(row: Any, db=None) -> None:
    """resume/extend 前确认旧作业线程已真正退出，避免两个线程写同一会话。

    多 worker：本进程内存查不到 ≠ 作业已死 —— 可能跑在其它进程。DB 租约心跳
    （factor/job_lease.py）仍新鲜的会话行按"活跃"拦截；心跳 NULL/过期视为
    崩溃残留，放行 resume。db 传调用方会话，与请求同事务读一致。
    """
    if not row.backend_job_id:
        return
    status = _manager_for(row.mode).get_status(row.backend_job_id)
    if status and status.get("status") in {"pending", "running"}:
        raise service.ResearchError("bad_state", "上一个作业仍在退出中，请稍后重试继续/延期操作")
    if job_lease.has_fresh_session_lease(row.backend_job_id, db=db):
        raise service.ResearchError("bad_state", "上一个作业仍在其它进程执行中，请稍后重试继续/延期操作")


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
            # 会话行的 DB 租约心跳 + 跨进程 cancel/pause 消费（factor/job_lease.py）
            lease="session",
            on_stop_signal=lambda sig: getattr(control, sig).set(),
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
    # 场景白名单：未实现的显式 400，禁止静默降级成 factor
    if payload.scenario not in ("factor", "strategy", "model"):
        raise HTTPException(
            status_code=400,
            detail={
                "code": "scenario_not_supported",
                "message": f"场景 {payload.scenario} 尚未实现（当前支持 factor / strategy / model）",
            },
        )
    # quick 是 factor 批量挖掘链路，strategy / model 只有 deep 闭环
    if payload.scenario in ("strategy", "model") and payload.mode == "quick":
        raise HTTPException(
            status_code=400,
            detail={
                "code": "mode_not_supported",
                "message": f"{payload.scenario} 场景暂不支持 quick 模式，请使用 deep 模式",
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
    # 种子因子必须真实存在：不校验会把不存在的名字直接写进 propose 提示词
    if payload.seed_factor and load_seed_factor(payload.seed_factor) is None:
        raise HTTPException(
            status_code=400,
            detail={"code": "unknown_factor", "message": f"种子因子 {payload.seed_factor} 不存在于因子库"},
        )
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
    _bind_job(session_id, job_id)
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
        # 批量取 best trial，替代逐行 best_trial_for 的 N+1
        best_map = service.best_trials_for(db, rows)
        for row in rows:
            sessions.append(service.session_to_dict(row, db=db, best_trial=best_map.get(row.best_trial_id)))
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
        data = service.session_to_dict(row, db=db, best_trial=best, trials=trials, include_trials=True)
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


@router.post(
    "/sessions/{session_id}/trials/batch",
    response_model=ApiResponse,
    summary="批量取 trial（对比视图用）",
    description="一次取 2–5 条同一会话的 trial（含代码）供并排对比；跨会话 id 返回 404。",
)
def batch_trials(
    session_id: int,
    payload: ResearchTrialBatchReq,
    current_user: dict = Depends(get_current_user),
) -> ApiResponse:
    with get_db_session() as db:
        try:
            service.get_session_row(db, session_id, _owner(current_user))
            rows = service.get_trials_for_session(db, session_id, payload.trial_ids)
        except service.ResearchError as exc:
            raise _http_error(exc) from exc
        trials = [service.trial_to_dict(row, include_code=True) for row in rows]
    return ApiResponse(code=0, message="ok", data={"trials": trials})


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


@router.post(
    "/sessions/{session_id}/trials/{trial_id}/replay",
    response_model=ApiResponse,
    summary="回放历史 trial",
    description=(
        "用原 trial 的代码 + 会话配置里的数据窗口/评估参数重跑评估，"
        "结果落成一条 replay_of_id 关联的新 trial，不覆盖原记录。"
        "缺 start/end/test_ratio 等非阻断字段时返回 partial=true（部分复现）；"
        "symbols/interval 缺失或原 trial 无代码时返回 409。"
    ),
)
def replay_trial(
    session_id: int,
    trial_id: int,
    current_user: dict = Depends(get_current_user),
) -> ApiResponse:
    with get_db_session() as db:
        try:
            data = replay.replay_trial(
                db,
                session_id=session_id,
                trial_id=trial_id,
                owner_id=_owner(current_user),
            )
        except service.ResearchError as exc:
            raise _http_error(exc) from exc
    return ApiResponse(code=0, message="ok", data=data)


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
            # 跨进程投递：若作业跑在其它进程，持有进程的心跳线程会消费 pause 标志
            # （标志保留在行上（本地 ctrl 未消费时）不引起问题，心跳线程清零）
            if row.backend_job_id:
                job_lease.request_session_stop(row.backend_job_id, "pause", db=db)
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
            _ensure_no_active_job(row, db=db)
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
    _bind_job(session_id, job_id)
    return ApiResponse(code=0, message="ok", data={"session_id": session_id, "job_id": job_id})


def _bind_job(session_id: int, job_id: str) -> None:
    """把新 job 绑定到会话行，并初始化租约影子状态（factor/job_lease.py）。

    清残留 stop 标志（上一个作业终态后心跳线程不再 poll，标志可能未被清零，
    不清会让新作业一启动就被误取消/暂停）+ 写首跳心跳（消除跨进程判活窗口）。
    """
    with get_db_session() as db:
        service.update_session_fields(db, session_id, backend_job_id=job_id)
        job_lease.clear_session_stop(session_id, db=db)
        job_lease.mark_session_heartbeat(job_id, db=db)
        db.commit()


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
            # 跨进程投递：作业跑在其它进程时，本地 ctrl 为 None，靠 DB 标志传递取消
            if row.backend_job_id:
                job_lease.request_session_stop(row.backend_job_id, "cancel", db=db)
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
            _ensure_no_active_job(row, db=db)
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
    _bind_job(session_id, job_id)
    return ApiResponse(code=0, message="ok", data={"session_id": session_id, "job_id": job_id})


async def research_ws_endpoint(websocket: WebSocket, token: str | None = Query(None)) -> None:
    """研究事件实时推送（main.py 挂载到 /ws/research）。

    认证与 SSE 一致：query 带 ?token=<jwt>（浏览器 WS 无法自定义请求头）。
    服务端心跳约定：收到客户端任意消息统一回 pong（前端 30s 发 ping，
    60s 未收到 pong 会断开重连）。事件不补发——事件已持久化，断线重连后
    前端走 /events 增量轮询续读。
    """
    try:
        current_user = await authenticate_request(websocket, token=token)
    except HTTPException:
        # WS 握手无法返回 HTTP 状态码，accept 后按 4401 关闭区分认证失败
        await websocket.accept()
        await websocket.close(code=4401)
        return

    owner = _owner(current_user)
    # 发布桥绑定主事件循环：worker 线程 append_event 后经此 loop 投递到下面的队列
    research_ws.set_event_loop(asyncio.get_running_loop())
    queue = research_ws.subscribe(owner)
    await websocket.accept()
    recv_task: asyncio.Task | None = None
    queue_task: asyncio.Task | None = None
    try:
        await websocket.send_json({"type": "connected", "data": {"owner": owner}})
        recv_task = asyncio.create_task(websocket.receive_text())
        queue_task = asyncio.create_task(queue.get())
        while True:
            # 双源等待：客户端消息（心跳）与推送事件谁先到处理谁
            done, _ = await asyncio.wait({recv_task, queue_task}, return_when=asyncio.FIRST_COMPLETED)
            if recv_task in done:
                try:
                    await websocket.send_json({"type": "pong"})
                except Exception:
                    break
                recv_task = asyncio.create_task(websocket.receive_text())
            if queue_task in done:
                await websocket.send_json({"type": "research.event", "data": queue_task.result()})
                queue_task = asyncio.create_task(queue.get())
    except Exception:
        pass  # 客户端断开/发送失败统一走 finally 清理
    finally:
        for task in (recv_task, queue_task):
            if task:
                task.cancel()
        research_ws.unsubscribe(owner, queue)
        try:
            await websocket.close()
        except Exception:
            pass
