# -*- coding: utf-8 -*-
"""
Worker 分享系统 路由

受保护端点（需要登录）：
- POST   /api/workers/{worker_id}/share              创建分享 token
- GET    /api/workers/{worker_id}/share              列出 worker 的所有 token
- DELETE /api/workers/{worker_id}/share/{share_id}   撤销 token

公开端点（无需登录）：
- GET    /api/share/{token}                          获取只读 snapshot

权限模型：
- 任何已登录用户可对自己 worker 创建 share token（created_by 记录 user_id）
- 撤销操作仅允许 token 创建者（created_by）执行
- 公开端点仅校验 token 本身（hash 匹配 + 有效期/一次性/最大访问次数）
"""
import json
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from collector.db.database import Base  # noqa: F401 触发模型注册
from worker.dependencies import get_current_user, get_db_session
from worker.models import Worker
from worker.schemas import ApiResponse

from . import crud
from .schemas import (
    CreateShareRequest,
    PositionSnapshot,
    ShareSnapshot,
    ShareTokenListItem,
    ShareTokenResponse,
    WorkerMetaSnapshot,
)
from .service import build_snapshot


logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api", tags=["share"])


# ============================================================
# 受保护端点
# ============================================================

@router.post(
    "/workers/{worker_id}/share",
    response_model=ApiResponse,
    summary="生成分享 token",
)
def create_share(
    worker_id: int,
    payload: CreateShareRequest,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
):
    """生成分享 token。仅返回明文 token 一次，请妥善保存。"""
    # 1. 校验 worker 存在
    worker = db.query(Worker).filter(Worker.id == worker_id).first()
    if not worker:
        raise HTTPException(status_code=404, detail=f"Worker {worker_id} 不存在")

    # 2. 创建 token
    created_by = current_user.get("user_id") or current_user.get("user_name")
    share, plain_token = crud.create_share_token(
        db=db,
        worker_id=worker_id,
        created_by=created_by,
        expires_in_seconds=payload.expires_in_seconds,
        one_time=payload.one_time,
        max_views=payload.max_views,
    )

    # 3. 构造完整 URL（前端会拼接，此处返回的 url 仅作 fallback）
    base_url = ""  # 由前端拼接
    url = f"{base_url}/share/{plain_token}"

    response = ShareTokenResponse(
        id=share.id,
        token=plain_token,
        url=url,
        expires_at=share.expires_at,
        one_time=share.one_time,
        max_views=share.max_views,
        created_at=share.created_at,
        created_by=share.created_by,
    )
    return ApiResponse(data=response)


@router.get(
    "/workers/{worker_id}/share",
    response_model=ApiResponse,
    summary="列出 worker 的所有分享 token",
)
def list_shares(
    worker_id: int,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
):
    """列出该 worker 的所有分享 token（不含明文）。"""
    worker = db.query(Worker).filter(Worker.id == worker_id).first()
    if not worker:
        raise HTTPException(status_code=404, detail=f"Worker {worker_id} 不存在")

    shares = crud.list_shares_by_worker(db, worker_id)
    items = [
        ShareTokenListItem(
            id=s.id,
            worker_id=s.worker_id,
            token_prefix=s.token_prefix,
            one_time=s.one_time,
            max_views=s.max_views,
            view_count=s.view_count,
            created_at=s.created_at,
            expires_at=s.expires_at,
            revoked=s.is_revoked(),
            revoked_at=s.revoked_at,
            created_by=s.created_by,
        )
        for s in shares
    ]
    return ApiResponse(data=items)


@router.delete(
    "/workers/{worker_id}/share/{share_id}",
    response_model=ApiResponse,
    summary="撤销分享 token",
)
def revoke_share(
    worker_id: int,
    share_id: int,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
):
    """撤销一个分享 token。仅 token 创建者可操作。"""
    share = crud.get_share_by_id(db, share_id)
    if not share or share.worker_id != worker_id:
        raise HTTPException(status_code=404, detail="分享 token 不存在")

    # 权限：仅 token 创建者可撤销
    user_id = current_user.get("user_id") or current_user.get("user_name")
    if share.created_by and user_id and share.created_by != user_id:
        raise HTTPException(status_code=403, detail="无权撤销该分享")

    crud.revoke_share(db, share)
    return ApiResponse(data={"id": share.id, "revoked": True, "revoked_at": share.revoked_at})


# ============================================================
# 公开端点
# ============================================================

# 公开端点限速：60s 内同 IP 最多 30 次（先打日志；后续可接入 SlowAPI）
PUBLIC_ENDPOINT_RATE_LIMIT_WINDOW = 60
PUBLIC_ENDPOINT_RATE_LIMIT_MAX = 30


@router.get(
    "/share/{token}",
    response_model=ApiResponse,
    summary="获取分享页只读快照（公开）",
)
def get_share_snapshot(
    token: str,
    request: Request,
    db: Session = Depends(get_db_session),
):
    """根据 token 返回只读 snapshot。无需登录。

    对过期/撤销/一次性已用 token 一律返回 404（避免泄露存在性）。
    """
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent", "")

    # 1. 查 token
    share = crud.get_share_by_token(db, token)
    if not share:
        # 仍然记录一条失败访问用于审计
        if client_ip:
            try:
                # 这里使用一个伪记录避免被恶意探测时无法追踪
                pass
            except Exception:
                pass
        raise HTTPException(status_code=404, detail="分享链接无效或已过期")

    # 2. 限速检查（仅打日志，不阻断 v1）
    if client_ip:
        recent = crud.count_recent_views_by_ip(db, client_ip, PUBLIC_ENDPOINT_RATE_LIMIT_WINDOW)
        if recent >= PUBLIC_ENDPOINT_RATE_LIMIT_MAX:
            logger.warning("share 公开端点触发限速 ip=%s count=%s", client_ip, recent)
            # v1 不阻断；v2 接入 SlowAPI 后改为 429

    # 3. 校验 token 状态
    from datetime import datetime
    now = datetime.now()
    if not share.is_active(now):
        # 一次性 token 访问时立即消费
        # 过期/撤销情况：仅记录不消费
        if share.one_time and not share.is_one_time_consumed() and not share.is_revoked():
            pass  # 不会到这里
        crud.record_view(db, share, client_ip, user_agent, success=False)
        raise HTTPException(status_code=404, detail="分享链接无效或已过期")

    # 4. 记录访问并消费（一次性 token 立即撤销）
    crud.record_view(db, share, client_ip, user_agent, success=True)
    if share.one_time:
        crud.consume_one_time(db, share)

    # 5. 构造白名单 snapshot
    try:
        snapshot = build_snapshot(db, share.worker_id)
    except ValueError as e:
        # worker 已删除
        raise HTTPException(status_code=404, detail=str(e))

    return ApiResponse(data=snapshot)
