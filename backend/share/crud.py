"""
Worker 分享系统 CRUD

token 生成遵循：
- 256 bit 熵：secrets.token_urlsafe(32)
- 数据库仅存 SHA256(token)，不存明文

说明：
- 公开只读页已下线，分享功能完全走 quantcell.top 远端分发
- 本地不再记录 ShareView 访问审计（远端 quantcell.top 端负责统计）
- view_count 仍保留但不再自增，仅作为兼容字段
"""

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import desc

from .models import ShareToken

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _hash_token(token: str) -> str:
    """对 token 进行 SHA256 哈希（数据库只存哈希）"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_token() -> str:
    """生成 256 bit 熵的随机 token"""
    return secrets.token_urlsafe(32)


def create_share_token(
    db: Session,
    worker_id: int,
    created_by: str | None,
    expires_in_seconds: int | None,
    one_time: bool,
    max_views: int | None = None,
) -> tuple[ShareToken, str]:
    """创建分享 token

    Returns:
        (ShareToken 实例, 明文 token)
    """
    token = generate_token()
    token_hash = _hash_token(token)
    token_prefix = token[:8]

    expires_at = None
    if expires_in_seconds:
        expires_at = datetime.now() + timedelta(seconds=expires_in_seconds)

    share = ShareToken(
        worker_id=worker_id,
        token_hash=token_hash,
        token_prefix=token_prefix,
        one_time=one_time,
        max_views=max_views,
        created_by=created_by,
        expires_at=expires_at,
    )
    db.add(share)
    db.commit()
    db.refresh(share)
    return share, token


def get_share_by_id(db: Session, share_id: int) -> ShareToken | None:
    """通过 id 查询"""
    return db.query(ShareToken).filter(ShareToken.id == share_id).first()


def get_share_by_token(db: Session, token: str) -> ShareToken | None:
    """通过明文 token 查询（内部哈希匹配）"""
    if not token:
        return None
    token_hash = _hash_token(token)
    return db.query(ShareToken).filter(ShareToken.token_hash == token_hash).first()


def list_shares_by_worker(db: Session, worker_id: int) -> list[ShareToken]:
    """列出指定 worker 的所有分享 token（按创建时间倒序）"""
    return db.query(ShareToken).filter(ShareToken.worker_id == worker_id).order_by(desc(ShareToken.created_at)).all()


def revoke_share(db: Session, share: ShareToken) -> ShareToken:
    """撤销一个分享 token

    撤销后 is_active() 永远返回 False
    """
    if share.revoked_at is None:
        share.revoked_at = datetime.now()
        db.add(share)
        db.commit()
        db.refresh(share)
    return share


def delete_share(db: Session, share: ShareToken) -> None:
    """物理删除一个分享 token

    与 revoke 的区别：revoke 仅标记 revoked_at,记录仍在表中;delete 会从数据库移除记录。
    远端撤销由路由层在调用本函数前完成 best-effort 处理。
    """
    db.delete(share)
    db.commit()
