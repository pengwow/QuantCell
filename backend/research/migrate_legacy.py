"""旧 LLM 挖掘历史（factor_mining_runs）→ 研究会话的一次性迁移（PRD P2-④）。

口径与 quick 模式一致：候选经 map_candidates_to_trials 落 trial、不自动决策、
best_trial_id 留空（依赖人工 promote）；failed/interrupted 的 run 迁成 failed 会话。

幂等：
- 会话级锚点 = config_json 里的 "migrated_job_id": "<job_id>"（config_json 是 Text
  列，服务端不改写格式，按同一段字符串 contains 查找；job_id 是 uuid 无通配符风险）；
- trial 级兜底 = (session_id, loop_idx, candidate_idx) 唯一索引 + get_or_add_trial。
中途失败时回删刚建的会话，避免留下"有锚点但 trial 不全"的半成品（重跑才能补齐）。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from factor.models import FactorMiningRun
from research import service
from research.models import ResearchSession
from research.quick import map_candidates_to_trials, session_cost_from_stats

MARKER_KEY = "migrated_job_id"
# 仍在跑的 run 不迁：它的结果还没落库，迁了只会得到空会话
SKIP_STATUSES = ("running",)


def _dumps(payload: dict[str, Any]) -> str:
    """config_json 序列化口径与 service 保持一致（ensure_ascii=False、默认分隔符）。"""
    return json.dumps(payload, ensure_ascii=False)


def find_migrated_session(db: Session, job_id: str) -> ResearchSession | None:
    """按幂等锚点找已迁移会话。ponytail: contains 是全表 LIKE，会话量级 <1e3 可接受。"""
    marker = f'"{MARKER_KEY}": "{job_id}"'
    return db.query(ResearchSession).filter(ResearchSession.config_json.contains(marker)).one_or_none()


def _loads(raw: str | None) -> dict[str, Any]:
    try:
        return json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return {}


def migrate_run(db: Session, run: FactorMiningRun, owner_id: str) -> dict[str, Any]:
    """迁移单条 run，返回 {session_id, trials, skipped}；skipped 非 None 表示未做写入。"""
    existing = find_migrated_session(db, run.job_id)
    if existing is not None:
        return {"session_id": existing.id, "trials": 0, "skipped": "already_migrated"}
    if run.status in SKIP_STATUSES:
        return {"session_id": None, "trials": 0, "skipped": "still_running"}

    params = _loads(run.params_json)
    result = _loads(run.result_json)
    stats = _loads(run.stats_json)
    candidates = result.get("candidates") or []
    config = {**params, MARKER_KEY: run.job_id, "migrated_at": datetime.now(UTC).isoformat()}

    row = service.create_session(
        db,
        owner_id=owner_id,
        name=f"挖掘迁移 {run.job_id[:8]}",
        mode="quick",
        scenario="factor",
        config=config,
        n_candidates=len(candidates) or 1,
    )
    try:
        # 沿用真实迁移链 pending→running→completed/failed，保证状态机合法
        service.set_session_status(db, row, "running")
        trials = 0
        if run.status == "completed":
            service.set_session_status(db, row, "completed")
            for fields in map_candidates_to_trials(candidates, quick_run_id=run.id):
                service.get_or_add_trial(db, row.id, fields)
                trials += 1
            calls, tokens = session_cost_from_stats(stats)
            service.update_session_fields(db, row.id, llm_calls=calls, token_used=tokens, loop_done=1)
        else:
            # failed / interrupted：没有产物，只留轨迹
            service.set_session_status(db, row, "failed", error=(run.error or run.status or "")[:2000])
    except Exception:
        # 半成品会话会因锚点命中被后续重跑跳过，直接回删保证重跑能补齐
        db.delete(row)
        db.commit()
        raise
    return {"session_id": row.id, "trials": trials, "skipped": None}
