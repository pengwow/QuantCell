"""研究任务的线程池与 runner 装配。

quick 复用现有 factor job_manager（与 llm_mine 同一池）；
deep 使用独立 2 worker 池，避免互相饿死（PRD §9）。
"""

from __future__ import annotations

from typing import Any

from axon_bridge.llm import create_llm_backend
from factor.job_manager import FactorJobManager
from research import consts, service
from research.loop import LoopDeps, ResearchLoop, default_llm_call, default_mining_fn
from research.scenario import get_scenario
from utils.db_session import get_db_session
from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)

research_job_manager = FactorJobManager(max_workers=consts.DEEP_JOB_WORKERS)


def create_backend(llm_cfg: dict[str, Any], cfg: dict[str, Any]):
    """与现有挖掘一致的 backend 参数；reasoning 模型留足 16k 输出预算。"""
    temperature = cfg.get("temperature")
    return create_llm_backend(
        api_key=llm_cfg["api_key"],
        base_url=llm_cfg["base_url"],
        model=llm_cfg["model"],
        # 显式 0.0 是合法温度，不能用 `or` 覆盖成默认值
        temperature=float(consts.DEEP_TEMPERATURE if temperature is None else temperature),
        max_tokens=16384,
        timeout_secs=180,
    )


def build_deps(*, backend: Any, mode: str, cfg: dict[str, Any], model_name: str) -> LoopDeps:
    scenario = get_scenario(str(cfg.get("scenario") or "factor"))
    if mode == "quick" and not cfg.get("extend_deep"):
        # quick 会话 extend 后追加的轮次走 deep 编排，需要 llm_call 而不是 mining_fn
        return LoopDeps(
            mining_fn=default_mining_fn(backend, model_name),
            scenario=scenario,
            model_name=model_name,
        )
    return LoopDeps(
        llm_call=default_llm_call(backend),
        scenario=scenario,
        model_name=model_name,
    )


def make_runner(
    *,
    session_id: int,
    mode: str,
    cfg: dict[str, Any],
    llm_cfg: dict[str, Any],
    control: service.Control,
):
    """返回 FactorJobManager 需要的 Runner 闭包。"""

    def runner(on_progress, _on_stage, on_event=None):
        backend = create_backend(llm_cfg, cfg)
        deps = build_deps(
            backend=backend,
            mode=mode,
            cfg=cfg,
            model_name=str(llm_cfg.get("model") or ""),
        )
        # 过程事件持久化到 research_events：多 worker 部署下只有持有 job 的进程能看到
        # 进程内缓冲，写库后任一进程都能按 seq 增量读到（局限见 models.ResearchEvent）
        deps.event_fn = lambda stage, msg: _persist_event(session_id, stage, msg)
        ResearchLoop(session_id, deps).run(control)
        return {"session_id": session_id}

    return runner


def _persist_event(session_id: int, stage: str, msg: str) -> None:
    """事件落库；写失败只记日志，不影响研究主回路。"""
    try:
        with get_db_session() as db:
            service.append_event(db, session_id, "info", stage, msg)
    except Exception:
        logger.exception(f"[研究] 事件落库失败 session={session_id}")
