"""跨进程作业租约：多 uvicorn worker 部署下作业状态的 DB 影子（PRD §9）。

作业执行真相仍在本进程内存（FactorJobManager），内存 dict 只在持有进程可见。
本模块给两张作业表加最小影子状态，让其它进程能正确判活与投递控制信号：

- ``heartbeat_at``：运行中的作业由持有进程的守护线程周期刷新；其它进程以
  心跳新旧判断"这个 job 是否还活着"，取代原来"内存查不到 = 已死"的错误假设
  （否则挖掘列表的懒修正会把别的进程正在跑的任务误标 interrupted，研究会的
  resume/extend 会误放行导致双跑）。
- ``cancel_requested`` / ``pause_requested``（仅 research_sessions）：cancel/pause
  路由在任意进程写标志；持有进程的心跳线程下一 tick 消费标志并拉起本地
  control 信号，loop 在最近的 step 边界停下（复用既有 CancelSignal/PauseSignal
  路径，loop 无需改动）。

所有函数都接受可选 ``db``：传入时使用调用方会话（与调用方同事务，读一致也
少一次连接），不传时自开短会话。测试可用 SQLite 内存库直接传 db。
"""

from __future__ import annotations

import time

from sqlalchemy import text
from sqlalchemy.orm import Session

from utils.db_session import get_db_session
from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)

# 心跳 tick 与判活阈值：阈值远大于 tick，容忍若干次写失败
LEASE_TICK_SECONDS = 20.0
LEASE_STALE_SECONDS = 75.0

# 研究会话的跨进程控制信号 → 对应 DB 列（白名单，防注入）
_SESSION_SIGNAL_COLUMNS = {
    "cancel": "cancel_requested",
    "pause": "pause_requested",
}


def ensure_lease_columns(session: Session, db_type: str) -> None:
    """给 factor_mining_runs / research_sessions 补齐租约影子列（幂等）。

    create_all 不会 ALTER 已有表，存量库由启动迁移（run_migrations）调用本函数补列。
    """
    wanted = [
        ("factor_mining_runs", "heartbeat_at", "REAL"),
        ("research_sessions", "heartbeat_at", "REAL"),
        ("research_sessions", "cancel_requested", "INTEGER DEFAULT 0"),
        ("research_sessions", "pause_requested", "INTEGER DEFAULT 0"),
    ]
    for table, column, ddl in wanted:
        try:
            if db_type == "sqlite":
                table_exists = session.execute(
                    text("SELECT name FROM sqlite_master WHERE type='table' AND name=:t"),
                    {"t": table},
                ).fetchone()
                if not table_exists:
                    logger.info(f"{table} 表不存在（首次建库由 create_all 负责），跳过 {column} 迁移")
                    continue
                exists = session.execute(
                    text(f"SELECT name FROM pragma_table_info('{table}') WHERE name=:c"),
                    {"c": column},
                ).fetchone()
            else:
                exists = session.execute(
                    text("SELECT column_name FROM information_schema.columns WHERE table_name=:t AND column_name=:c"),
                    {"t": table, "c": column},
                ).fetchone()
            if exists:
                continue
            session.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
            session.commit()
            logger.info(f"{table}.{column} 租约列添加成功")
        except Exception as e:
            logger.error(f"添加 {table}.{column} 租约列失败: {e}")
            session.rollback()


# ---------- 心跳 ----------


def mark_mining_heartbeat(job_id: str, *, db: Session | None = None) -> None:
    """刷新挖掘作业心跳；行不存在或已终态时自然匹配不到（status 限定 running）。"""
    stmt = text("UPDATE factor_mining_runs SET heartbeat_at=:now WHERE job_id=:jid AND status='running'")
    _exec(stmt, {"now": time.time(), "jid": job_id}, db)


def mark_session_heartbeat(job_id: str, *, db: Session | None = None) -> None:
    """刷新研究会话作业心跳；行不存在或已终态时自然匹配不到（status 限定 running）。"""
    stmt = text("UPDATE research_sessions SET heartbeat_at=:now WHERE backend_job_id=:jid AND status='running'")
    _exec(stmt, {"now": time.time(), "jid": job_id}, db)


def _exec(stmt, params: dict, db: Session | None) -> None:
    if db is not None:
        db.execute(stmt, params)
        return
    with get_db_session() as session:
        session.execute(stmt, params)
        session.commit()


# ---------- 判活 ----------


def has_fresh_mining_lease(
    job_id: str, *, db: Session | None = None, stale_seconds: float = LEASE_STALE_SECONDS
) -> bool:
    """挖掘作业是否仍被某个进程持有（行 running 且心跳在 stale_seconds 内）。"""
    return _lease_alive(
        "SELECT status, heartbeat_at FROM factor_mining_runs WHERE job_id=:jid",
        job_id,
        db=db,
        stale_seconds=stale_seconds,
    )


def has_fresh_session_lease(
    job_id: str, *, db: Session | None = None, stale_seconds: float = LEASE_STALE_SECONDS
) -> bool:
    """研究会话作业是否仍被某个进程持有（行运行中且心跳新鲜）。

    heartbeat_at 为 NULL（从未写过心跳的崩溃残留行）视为不活跃，放行 resume。
    """
    return _lease_alive(
        "SELECT status, heartbeat_at FROM research_sessions WHERE backend_job_id=:jid",
        job_id,
        db=db,
        stale_seconds=stale_seconds,
    )


def _lease_alive(stmt: str, job_id: str, *, db: Session | None, stale_seconds: float) -> bool:
    def _query(session: Session) -> bool:
        row = session.execute(text(stmt), {"jid": job_id}).fetchone()
        if not row or row[0] != "running" or row[1] is None:
            return False
        return bool(time.time() - float(row[1]) <= stale_seconds)

    if db is not None:
        return _query(db)
    with get_db_session() as session:
        return _query(session)


# ---------- 跨进程 cancel/pause 标志（仅 research_sessions） ----------


def request_session_stop(job_id: str, signal: str, *, db: Session | None = None) -> None:
    """写入跨进程 stop 标志；signal ∈ {"cancel", "pause"}，由持有进程心跳线程消费。"""
    column = _SESSION_SIGNAL_COLUMNS[signal]
    _exec(
        text(f"UPDATE research_sessions SET {column}=1 WHERE backend_job_id=:jid"),
        {"jid": job_id},
        db,
    )


def consume_session_signal(job_id: str, signal: str, *, db: Session | None = None) -> bool:
    """读取并清零跨进程 stop 标志；True 表示持有进程需要拉起本地 control 信号。"""
    column = _SESSION_SIGNAL_COLUMNS[signal]
    if db is not None:
        return _consume(db, column, job_id)
    with get_db_session() as session:
        return _consume(session, column, job_id)


def _consume(session: Session, column: str, job_id: str) -> bool:
    row = session.execute(
        text(f"SELECT {column} FROM research_sessions WHERE backend_job_id=:jid"), {"jid": job_id}
    ).fetchone()
    if not row or not row[0]:
        return False
    session.execute(text(f"UPDATE research_sessions SET {column}=0 WHERE backend_job_id=:jid"), {"jid": job_id})
    session.commit()
    return True


def clear_session_stop(session_id: int, *, db: Session | None = None) -> None:
    """新作业绑定 backend_job_id 前清零两个 stop 标志。

    作业退出（终态）后心跳线程不再 poll，标志可能残留；不清零会在新作业
    绑定 backend_job_id 后被误消费，导致新作业一启动就被取消/暂停。
    """
    _exec(
        text("UPDATE research_sessions SET cancel_requested=0, pause_requested=0 WHERE id=:sid"),
        {"sid": session_id},
        db,
    )


# ---------- 作业类型 → 租约钩子（FactorJobManager 心跳线程按 job.lease 查用） ----------

LEASE_HOOKS: dict[str, dict] = {
    # factor_mining_runs 挖掘作业：只写心跳（挖掘任务暂无 cancel 通道，信号钩子空转）
    "mining": {"heartbeat": mark_mining_heartbeat, "poll_signal": lambda *_: False},
    # research_sessions 会话作业：心跳 + 消费跨进程 cancel/pause
    "session": {"heartbeat": mark_session_heartbeat, "poll_signal": consume_session_signal},
}
