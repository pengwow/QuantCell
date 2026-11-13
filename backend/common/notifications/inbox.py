"""站内收件箱读写：落库、游标分页查询、全局已读水位

单管理员自部署场景，全站共享一个收件箱（无 user_id 隔离）。
未读判定 = id > notification_state.last_read_id（单调 id 水位，
详见 inbox_models.py 模块注释里不用时间戳的原因）。
"""

import typing

from sqlalchemy import delete, func, select

from utils.db_session import use_db_session
from utils.logger import LogType, get_logger

from .inbox_models import InboxNotification, NotificationState

logger = get_logger(__name__, LogType.APPLICATION)

_STATE_ID = 1  # notification_state 单行表的主键约定值


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
        # sqlite 存的是 naive UTC，按 alerts_routes 惯例补 Z 后缀声明 UTC
        "created_at": row.created_at.isoformat() + "Z" if row.created_at else None,
    }


def _count_unread(db: typing.Any) -> int:
    """当前未读数 = id > last_read_id 的条数（无状态行视为全部未读）。"""
    stmt = select(func.count()).select_from(InboxNotification)
    state = db.get(NotificationState, _STATE_ID)
    if state is not None and state.last_read_id is not None:
        stmt = stmt.where(InboxNotification.id > state.last_read_id)
    return int(db.execute(stmt).scalar() or 0)


def list_inbox_notifications(
    limit: int = 20,
    before_id: int | None = None,
    db_session: typing.Any | None = None,
) -> dict:
    """游标分页拉取收件箱：按 id 倒序，before_id 表示取比它更旧的一页。

    返回 {items, unread_count, read_count, has_more}。
    read_count = 总数 - unread_count，供前端「清空已读」按钮判断是否可点。
    """
    with use_db_session(db_session) as db:
        # 多取一条判断 has_more，再截掉
        query = select(InboxNotification).order_by(InboxNotification.id.desc()).limit(limit + 1)
        if before_id is not None:
            query = query.where(InboxNotification.id < before_id)
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
    """全部已读：水位推到当前可见的最大通知 id；返回该 id（空箱为 0）。

    upsert notification_state 单行；空箱也建行（水位 0，后续新通知全部未读）。
    """
    with use_db_session(db_session) as db:
        max_id = db.execute(select(func.max(InboxNotification.id))).scalar() or 0
        state = db.get(NotificationState, _STATE_ID)
        if state is None:
            db.add(NotificationState(id=_STATE_ID, last_read_id=max_id))
        else:
            # 水位只前进不回退：防止并发删数据时把用户已读状态"读回来"
            state.last_read_id = max(max_id, state.last_read_id or 0)
        db.commit()
        return max_id


def delete_notification(notification_id: int, db_session: typing.Any | None = None) -> int | None:
    """删除单条站内通知（物理删除，通知是流水非审计数据）。

    返回删除后的全局未读数；条目不存在返回 None（路由层转 404）。
    notification_state 水位不动：id 单调自增，删中间行不会影响 id 水位判定。
    """
    with use_db_session(db_session) as db:
        row = db.get(InboxNotification, notification_id)
        if row is None:
            return None
        db.delete(row)
        db.commit()
        return _count_unread(db)


def clear_read_notifications(db_session: typing.Any | None = None) -> tuple[int, int]:
    """清空已读：物理删除 id <= last_read_id 的流水，保留未读。

    返回 (删除条数, 清空后的未读数)。无状态行（从未点过全部已读）时无事可做，返回 (0, 未读数)。
    """
    with use_db_session(db_session) as db:
        state = db.get(NotificationState, _STATE_ID)
        if state is None or state.last_read_id is None:
            return 0, _count_unread(db)
        result = db.execute(delete(InboxNotification).where(InboxNotification.id <= state.last_read_id))
        db.commit()
        return int(result.rowcount or 0), _count_unread(db)
