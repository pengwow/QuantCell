"""LLM 挖掘运行记录服务：running 行生命周期、终态落库、查询懒修正、序列化。

运行中任务真相源是 job_manager（内存）；本表是重连锚点 + 终态结果持久化。
所有方法无状态，Session 由调用方传入，风格对齐 catalog_service。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine, inspect, text
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

    MAX_EVENTS = 500

    def ensure_events_column(self, bind: Engine) -> None:
        """旧 SQLite 开发库补列（create_all 不会 ALTER 已有表）；幂等。

        生产 MySQL 由 alembic 19 迁移负责，这里对已存在列直接返回。
        """
        cols = {c["name"] for c in inspect(bind).get_columns("factor_mining_runs")}
        if "events_json" in cols:
            return
        with bind.begin() as conn:
            conn.execute(text("ALTER TABLE factor_mining_runs ADD COLUMN events_json TEXT"))

    def append_events(self, db: Session, job_id: str, events: list[dict[str, Any]]) -> None:
        """把一批事件并入 runs.events_json（单任务单线程写，读后追加写回，保留最新 500）。"""
        if not events:
            return
        self.ensure_events_column(db.bind)
        row = db.query(FactorMiningRun).filter_by(job_id=job_id).one_or_none()
        if row is None:
            # running 行可能尚未建好或记录已删：事件无法挂接，忽略
            return
        stored: list[dict[str, Any]] = json.loads(row.events_json) if row.events_json else []
        stored.extend(events)
        if len(stored) > self.MAX_EVENTS:
            stored = stored[-self.MAX_EVENTS :]
        row.events_json = json.dumps(stored, ensure_ascii=False)
        db.commit()

    # ---------- 查询与懒修正 ----------

    def _reconcile(self, db: Session, rows: list[FactorMiningRun]) -> None:
        """running 行对照内存 job 修正：内存无 → interrupted；内存终态 → 补写。

        已终态的 DB 行不查内存（completed 行不依赖内存 TTL，避免竞态）。
        """
        now = datetime.now(UTC)
        changed = False
        for row in rows:
            if row.status != RUNNING:
                continue
            job = job_manager.get(row.job_id)
            if job is None:
                row.status = INTERRUPTED
                row.finished_at = now
                changed = True
            elif job.status == JobStatus.COMPLETED and job.result is not None:
                row.status = COMPLETED
                row.stats_json = json.dumps(job.result.get("stats") or {}, ensure_ascii=False)
                row.result_json = json.dumps(job.result, ensure_ascii=False)
                row.finished_at = now
                changed = True
            elif job.status == JobStatus.FAILED:
                row.status = FAILED
                row.error = (job.error or "")[:10000]
                row.finished_at = now
                changed = True
        if changed:
            db.commit()

    def list_runs(self, db: Session, limit: int = 20, offset: int = 0) -> tuple[int, list[FactorMiningRun]]:
        running_rows = db.query(FactorMiningRun).filter(FactorMiningRun.status == RUNNING).all()
        self._reconcile(db, running_rows)
        total = db.query(FactorMiningRun).count()
        rows = (
            db.query(FactorMiningRun)
            .order_by(FactorMiningRun.created_at.desc(), FactorMiningRun.id.desc())
            .offset(max(offset, 0))
            .limit(min(max(limit, 1), 100))
            .all()
        )
        return total, rows

    def get_run(self, db: Session, run_id: int) -> FactorMiningRun:
        row = db.get(FactorMiningRun, run_id)
        if row is None:
            raise MiningRunError(f"挖掘记录不存在: {run_id}", "not_found")
        if row.status == RUNNING:
            self._reconcile(db, [row])
            db.refresh(row)
        return row

    def delete_run(self, db: Session, run_id: int) -> None:
        row = db.get(FactorMiningRun, run_id)
        if row is None:
            raise MiningRunError(f"挖掘记录不存在: {run_id}", "not_found")
        if row.status == RUNNING:
            raise MiningRunError(f"挖掘进行中，不能删除: {run_id}", "conflict")
        db.delete(row)
        db.commit()


def _dt(v: datetime | None) -> str | None:
    return v.isoformat() if v is not None else None


def _loads(s: str | None) -> Any:
    return json.loads(s) if s else None


def run_summary(row: FactorMiningRun) -> dict[str, Any]:
    """列表项：含参数与 stats 摘要，不含完整 result。"""
    return {
        "id": row.id,
        "job_id": row.job_id,
        "status": row.status,
        "params": _loads(row.params_json) or {},
        "stats": _loads(row.stats_json),
        "error": row.error,
        "created_at": _dt(row.created_at),
        "finished_at": _dt(row.finished_at),
    }


def run_detail(row: FactorMiningRun) -> dict[str, Any]:
    """详情：摘要 + 完整 result + 过程事件。"""
    return {
        **run_summary(row),
        "result": _loads(row.result_json),
        "events": _loads(row.events_json) or [],
    }
