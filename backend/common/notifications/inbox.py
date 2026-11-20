"""站内收件箱读写：落库、过滤分页查询、逐行 read_at 已读

单管理员自部署场景，全站共享一个收件箱（无 user_id 隔离）。
未读判定 = read_at IS NULL（迁移 48 起的逐行语义）。
旧的 notification_state 全局水位表停用：水位只能表达「全部已读」，
无法支持单条已读与「任务类通知已读即归档（processed_at）」。
"""

import typing
from datetime import UTC, datetime

from sqlalchemy import delete, func, select, update

from utils.db_session import use_db_session
from utils.logger import LogType, get_logger

from .inbox_models import TASK_TYPES, InboxNotification

logger = get_logger(__name__, LogType.APPLICATION)


def _now() -> datetime:
    return datetime.now(UTC)


def record_inbox_notification(
    title: str,
    content: str,
    level: str,
    source: str,
    db_session: typing.Any | None = None,
) -> bool:
    """落库一条站内通知。写库失败仅记日志，不阻塞渠道投递主链路。"""
    try:
        with use_db_session(db_session) as db:
            db.add(InboxNotification(title=title, content=content, level=level, source=source))
            db.commit()
        return True
    except Exception as e:  # 不能让落库失败影响通知投递
        logger.error(f"站内通知落库失败(不影响投递): {e}")
        return False


def _to_dict(row: InboxNotification) -> dict:
    return {
        "id": row.id,
        "title": row.title,
        "content": row.content,
        "level": row.level,
        "source": row.source,
        # 派生布尔：read 由 read_at 推出，任务类过滤与点击跳转依赖 source
        "read": row.read_at is not None,
        "processed": row.processed_at is not None,
        # sqlite 存的是 naive UTC，按 alerts_routes 惯例补 Z 后缀声明 UTC
        "created_at": row.created_at.isoformat() + "Z" if row.created_at else None,
    }


def _count_unread(db: typing.Any) -> int:
    """当前未读数 = read_at IS NULL 的条数。"""
    stmt = select(func.count()).select_from(InboxNotification).where(InboxNotification.read_at.is_(None))
    return int(db.execute(stmt).scalar() or 0)


def list_inbox_notifications(
    limit: int = 20,
    before_id: int | None = None,
    unread: bool | None = None,
    task_type: str | None = None,
    db_session: typing.Any | None = None,
) -> dict:
    """游标分页拉取收件箱：按 id 倒序，before_id 表示取比它更旧的一页。

    unread=True 仅未读 / False 仅已读 / None 全量；task_type 匹配 source 列
    （五个任务域常量见 TASK_TYPES）。返回 {items, unread_count, read_count, has_more}。
    """
    with use_db_session(db_session) as db:
        # 多取一条判断 has_more，再截掉
        query = select(InboxNotification).order_by(InboxNotification.id.desc()).limit(limit + 1)
        if before_id is not None:
            query = query.where(InboxNotification.id < before_id)
        if unread is True:
            query = query.where(InboxNotification.read_at.is_(None))
        elif unread is False:
            query = query.where(InboxNotification.read_at.is_not(None))
        if task_type:
            query = query.where(InboxNotification.source == task_type)
        rows = db.execute(query).scalars().all()
        has_more = len(rows) > limit
        rows = rows[:limit]

        unread_count = _count_unread(db)
        total = int(db.execute(select(func.count()).select_from(InboxNotification)).scalar() or 0)

        return {
            "items": [_to_dict(r) for r in rows],
            "unread_count": unread_count,
            "read_count": max(total - unread_count, 0),
            "has_more": has_more,
        }


def mark_inbox_read(db_session: typing.Any | None = None) -> int:
    """全部已读：批量置 read_at；返回置位行数。幂等：已读行不动。"""
    with use_db_session(db_session) as db:
        result = db.execute(update(InboxNotification).where(InboxNotification.read_at.is_(None)).values(read_at=_now()))
        db.commit()
        return int(result.rowcount or 0)


def mark_notification_read(notification_id: int, db_session: typing.Any | None = None) -> dict | None:
    """单条已读：置 read_at；任务类通知首次已读时同时置 processed_at（已读即归档）。

    幂等：已有 read_at 的行不再动 processed_at。返回条目 dict；不存在返回 None。
    """
    with use_db_session(db_session) as db:
        row = db.get(InboxNotification, notification_id)
        if row is None:
            return None
        if row.read_at is None:
            row.read_at = _now()
            if row.source in TASK_TYPES and row.processed_at is None:
                row.processed_at = _now()
            db.commit()
        return _to_dict(row)


def delete_notification(notification_id: int, db_session: typing.Any | None = None) -> int | None:
    """删除单条站内通知（物理删除，通知是流水非审计数据）。

    返回删除后的全局未读数；条目不存在返回 None（路由层转 404）。
    """
    with use_db_session(db_session) as db:
        row = db.get(InboxNotification, notification_id)
        if row is None:
            return None
        db.delete(row)
        db.commit()
        return _count_unread(db)


def clear_read_notifications(db_session: typing.Any | None = None) -> tuple[int, int]:
    """清空已读：物理删除 read_at 非空的流水，保留未读。

    返回 (删除条数, 清空后的未读数)。
    """
    with use_db_session(db_session) as db:
        result = db.execute(delete(InboxNotification).where(InboxNotification.read_at.is_not(None)))
        db.commit()
        return int(result.rowcount or 0), _count_unread(db)
