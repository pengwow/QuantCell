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
from .config import get_remote_config
from .remote_client import RemoteShareClient, RemoteShareError
from .schemas import (
    CreateShareRequest,
    PositionSnapshot,
    ShareSnapshot,
    ShareTokenListItem,
    ShareTokenResponse,
    WorkerMetaSnapshot,
)
from .service import build_snapshot, serialize_for_remote


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
    """生成分享 token。仅返回明文 token 一次，请妥善保存。

    行为：
    1. 本地 create_share_token 必成功
    2. 远端 quantcell.top 上传为 best-effort：
       - 成功 → short_url 写回，remote_status=UPLOADED
       - 失败 → remote_status=FAILED，remote_warning 反馈给前端，不阻断本地
    3. 远端未启用（缺 api_key/hmac_secret 或开关关闭） → LOCAL_ONLY 状态
    """
    # 1. 校验 worker 存在
    worker = db.query(Worker).filter(Worker.id == worker_id).first()
    if not worker:
        raise HTTPException(status_code=404, detail=f"Worker {worker_id} 不存在")

    # 2. 本地创建 token
    created_by = current_user.get("user_id") or current_user.get("user_name")
    share, plain_token = crud.create_share_token(
        db=db,
        worker_id=worker_id,
        created_by=created_by,
        expires_in_seconds=payload.expires_in_seconds,
        one_time=payload.one_time,
        max_views=payload.max_views,
    )

    # 3. 远端上传（best-effort）
    short_url: Optional[str] = None
    remote_status = "PENDING"
    remote_warning: Optional[str] = None

    remote_cfg = get_remote_config()
    if remote_cfg.is_ready:
        try:
            # 构造白名单 snapshot
            snapshot = build_snapshot(db, worker_id)
            snapshot = serialize_for_remote(snapshot)

            # 调远端
            client = RemoteShareClient(remote_cfg)
            result = client.upload_sync(  # 内部用 asyncio.run 跑 async
                snapshot=snapshot,
                token_hash=share.token_hash,
                worker_id=worker_id,
            )
            share.remote_id = result["remote_id"]
            share.short_url = result["short_url"]
            share.remote_status = "UPLOADED"
            share.remote_error = None
            short_url = result["short_url"]
            remote_status = "UPLOADED"
            logger.info("share 上传远端成功 id=%s short_url=%s", share.id, short_url)
        except RemoteShareError as e:
            share.remote_status = "FAILED"
            share.remote_error = str(e)[:500]
            remote_status = "FAILED"  # 必须同步更新响应变量，否则响应会显示 PENDING
            remote_warning = f"远端上传失败：{str(e)[:200]}"
            logger.warning("share 上传远端失败 id=%s err=%s", share.id, e)
        except Exception as e:  # noqa: BLE001  兜底避免上传异常影响主流程
            share.remote_status = "FAILED"
            share.remote_error = repr(e)[:500]
            remote_status = "FAILED"
            remote_warning = "远端上传异常"
            logger.exception("share 上传远端异常 id=%s", share.id)
        finally:
            db.add(share)
            db.commit()
            db.refresh(share)
    else:
        share.remote_status = "LOCAL_ONLY"
        remote_status = "LOCAL_ONLY"  # 必须同步更新响应变量
        db.add(share)
        db.commit()
        db.refresh(share)
        logger.info(
            "share 远端未启用，使用本地模式 id=%s reason=%s",
            share.id, remote_cfg.summary(),
        )

    # 4. 构造响应：url 优先用 short_url，否则用本地 fallback
    response = ShareTokenResponse(
        id=share.id,
        token=plain_token,
        url=short_url or f"/share/{plain_token}",  # 前端再补 origin
        short_url=short_url,
        remote_status=remote_status,
        remote_warning=remote_warning,
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
            short_url=s.short_url,
            remote_status=s.remote_status or "PENDING",
            remote_error=s.remote_error,
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
    """撤销一个分享 token。仅 token 创建者可操作。

    远端撤销为 best-effort：失败仅记录日志，不影响本地撤销结果。
    """
    share = crud.get_share_by_id(db, share_id)
    if not share or share.worker_id != worker_id:
        raise HTTPException(status_code=404, detail="分享 token 不存在")

    # 权限：仅 token 创建者可撤销
    user_id = current_user.get("user_id") or current_user.get("user_name")
    if share.created_by and user_id and share.created_by != user_id:
        raise HTTPException(status_code=403, detail="无权撤销该分享")

    # 1. 本地撤销
    crud.revoke_share(db, share)

    # 2. 远端撤销（best-effort）
    remote_revoked = False
    if share.remote_id and get_remote_config().is_ready:
        try:
            RemoteShareClient().revoke_sync(share.remote_id)
            share.remote_status = "REVOKED"
            share.remote_error = None
            remote_revoked = True
        except RemoteShareError as e:
            share.remote_error = f"远端撤销失败：{str(e)[:300]}"
            logger.warning("share 远端撤销失败 id=%s err=%s", share.id, e)
        except Exception as e:  # noqa: BLE001
            share.remote_error = f"远端撤销异常：{repr(e)[:300]}"
            logger.exception("share 远端撤销异常 id=%s", share.id)
        finally:
            db.add(share)
            db.commit()
            db.refresh(share)

    return ApiResponse(data={
        "id": share.id,
        "revoked": True,
        "revoked_at": share.revoked_at,
        "remote_revoked": remote_revoked,
        "remote_status": share.remote_status,
    })


@router.post(
    "/workers/{worker_id}/share/{share_id}/retry-remote",
    response_model=ApiResponse,
    summary="重新上传分享到 quantcell.top",
)
def retry_remote_upload(
    worker_id: int,
    share_id: int,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
):
    """在首次上传失败后，重新把已存在的 share 推送到 quantcell.top。

    与 create 不同：不生成新 token，复用原 share；只重推 snapshot。
    仅 token 创建者可操作。
    """
    share = crud.get_share_by_id(db, share_id)
    if not share or share.worker_id != worker_id:
        raise HTTPException(status_code=404, detail="分享 token 不存在")

    # 权限：仅 token 创建者
    user_id = current_user.get("user_id") or current_user.get("user_name")
    if share.created_by and user_id and share.created_by != user_id:
        raise HTTPException(status_code=403, detail="无权重推该分享")

    if share.is_revoked():
        raise HTTPException(status_code=400, detail="已撤销的 token 无法重推")

    if not get_remote_config().is_ready:
        raise HTTPException(status_code=400, detail="远端分享未启用或凭据未配置")

    # 重新构造 snapshot 并上传
    try:
        snapshot = build_snapshot(db, worker_id)
        snapshot = serialize_for_remote(snapshot)

        client = RemoteShareClient()
        result = client.upload_sync(
            snapshot=snapshot,
            token_hash=share.token_hash,
            worker_id=worker_id,
        )
        share.remote_id = result["remote_id"]
        share.short_url = result["short_url"]
        share.remote_status = "UPLOADED"
        share.remote_error = None
        db.add(share)
        db.commit()
        db.refresh(share)
        return ApiResponse(data={
            "id": share.id,
            "short_url": share.short_url,
            "remote_status": share.remote_status,
        })
    except RemoteShareError as e:
        share.remote_status = "FAILED"
        share.remote_error = str(e)[:500]
        db.add(share)
        db.commit()
        db.refresh(share)
        raise HTTPException(status_code=502, detail=f"远端上传失败：{str(e)[:200]}")
    except Exception as e:  # noqa: BLE001
        share.remote_status = "FAILED"
        share.remote_error = repr(e)[:500]
        db.add(share)
        db.commit()
        db.refresh(share)
        logger.exception("share 重推远端异常 id=%s", share.id)
        raise HTTPException(status_code=500, detail="远端上传异常")


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
