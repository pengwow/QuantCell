"""LLM 挖掘运行记录服务：running 行生命周期、终态落库、查询懒修正、序列化。

运行中任务真相源是 job_manager（内存）；本表是重连锚点 + 终态结果持久化。
所有方法无状态，Session 由调用方传入，风格对齐 catalog_service。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from factor.job_manager import JobStatus, job_manager
from factor.models import FactorMiningRun
from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)

RUNNING = "running"
COMPLETED = "completed"
FAILED = "failed"
INTERRUPTED = "interrupted"


class MiningRunError(Exception):
    """kind: not_found / conflict"""

    def __init__(self, message: str, kind: str):
        super().__init__(message)
        self.kind = kind


class MiningRunService:
    def create_running(self, db: Session, job_id: str, params: dict[str, Any]) -> FactorMiningRun:
        row = FactorMiningRun(
            job_id=job_id,
            status=RUNNING,
            params_json=json.dumps(params, ensure_ascii=False),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def mark_completed(self, db: Session, job_id: str, result: dict[str, Any]) -> None:
        row = db.query(FactorMiningRun).filter_by(job_id=job_id).one_or_none()
        if row is None:
            logger.warning(f"挖掘完成落库找不到运行记录: {job_id}")
            return
        row.status = COMPLETED
        row.stats_json = json.dumps(result.get("stats") or {}, ensure_ascii=False)
        row.result_json = json.dumps(result, ensure_ascii=False)
        row.finished_at = datetime.now(UTC)
        db.commit()

    def mark_failed(self, db: Session, job_id: str, error: str) -> None:
        row = db.query(FactorMiningRun).filter_by(job_id=job_id).one_or_none()
        if row is None:
            logger.warning(f"挖掘失败落库找不到运行记录: {job_id}")
            return
        row.status = FAILED
        row.error = (error or "")[:10000]
        row.finished_at = datetime.now(UTC)
        db.commit()
