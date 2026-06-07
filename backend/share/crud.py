# -*- coding: utf-8 -*-
"""
Worker 分享系统 CRUD

token 生成遵循：
- 256 bit 熵：secrets.token_urlsafe(32)
- 数据库仅存 SHA256(token)，不存明文
"""
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import and_, desc
from sqlalchemy.orm import Session

from .models import ShareToken, ShareView


def _hash_token(token: str) -> str:
    """对 token 进行 SHA256 哈希（数据库只存哈希）"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_token() -> str:
    """生成 256 bit 熵的随机 token"""
    return secrets.token_urlsafe(32)


def create_share_token(
    db: Session,
    worker_id: int,
    created_by: Optional[str],
    expires_in_seconds: Optional[int],
    one_time: bool,
    max_views: Optional[int] = None,
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


def get_share_by_id(db: Session, share_id: int) -> Optional[ShareToken]:
    """通过 id 查询"""
    return db.query(ShareToken).filter(ShareToken.id == share_id).first()


def get_share_by_token(db: Session, token: str) -> Optional[ShareToken]:
    """通过明文 token 查询（内部哈希匹配）"""
    if not token:
        return None
    token_hash = _hash_token(token)
    return db.query(ShareToken).filter(ShareToken.token_hash == token_hash).first()


def list_shares_by_worker(db: Session, worker_id: int) -> List[ShareToken]:
    """列出指定 worker 的所有分享 token（按创建时间倒序）"""
    return (
        db.query(ShareToken)
        .filter(ShareToken.worker_id == worker_id)
        .order_by(desc(ShareToken.created_at))
        .all()
    )


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


def _has_ip_viewed_today(db: Session, share: ShareToken, ip: Optional[str]) -> bool:
    """判断指定 IP 是否在当天已访问过此 token（成功访问）。

    用于实现"按 IP + 天"去重的访问次数统计：
    - 同一 IP 同一天重复访问（含刷新）不重复计数
    - 不同 IP 当天访问则计为新一次
    - 跨天会重新计为新一次
    - IP 为空时按"无来源"处理，返回 False（视为每次都计数，避免来源丢失）
    """
    if not ip:
        return False
    # 取当天 0 点（本地时区，datetime.now() 已是 naive local time）
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return (
        db.query(ShareView)
        .filter(
            ShareView.token_id == share.id,
            ShareView.ip == ip,
            ShareView.success.is_(True),
            ShareView.viewed_at >= today_start,
        )
        .first()
        is not None
    )


def record_view(
    db: Session,
    share: ShareToken,
    ip: Optional[str],
    user_agent: Optional[str],
    success: bool = True,
) -> bool:
    """记录一次查看（用于审计），并按"IP + 天"去重维护 view_count。

    Returns:
        bool: view_count 是否发生了递增
            - True  : 视为一次新的"独立访问"，view_count +1
            - False : 同 IP 当天重复访问，仅记录审计日志，不递增
    """
    view = ShareView(
        token_id=share.id,
        ip=ip,
        user_agent=user_agent,
        success=success,
    )
    db.add(view)

    # 成功访问才计入 view_count；失败访问仅做审计
    counted = False
    if success and not _has_ip_viewed_today(db, share, ip):
        share.view_count = (share.view_count or 0) + 1
        counted = True

    db.add(share)
    db.commit()
    return counted


def consume_one_time(db: Session, share: ShareToken) -> None:
    """一次性 token 已被访问，标记为已撤销"""
    share.revoked_at = datetime.now()
    db.add(share)
    db.commit()
    db.refresh(share)


def count_recent_views_by_ip(db: Session, ip: str, window_seconds: int = 60) -> int:
    """统计指定 IP 在最近 N 秒内的访问次数（用于限速）"""
    if not ip:
        return 0
    threshold = datetime.now() - timedelta(seconds=window_seconds)
    return (
        db.query(ShareView)
        .filter(and_(ShareView.ip == ip, ShareView.viewed_at >= threshold))
        .count()
    )
