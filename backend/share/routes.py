# -*- coding: utf-8 -*-
"""
Worker 分享系统 路由

受保护端点（需要登录）：
- POST   /api/workers/{worker_id}/share              创建分享 token
- GET    /api/workers/{worker_id}/share              列出 worker 的所有 token
- DELETE /api/workers/{worker_id}/share/{share_id}   撤销 token
- POST   /api/workers/{worker_id}/share/{share_id}/retry-remote  重新上传远端
- GET    /api/share/credentials/status               查询远端凭据状态
- POST   /api/share/credentials/generate             一键生成远端凭据

权限模型：
- 任何已登录用户可对自己 worker 创建 share token（created_by 记录 user_id）
- 撤销与重推操作仅允许 token 创建者（created_by）执行

说明：
- 公开只读页已下线，分享功能完全走 quantcell.top 远端分发
- 本地不再提供 GET /api/share/{token}
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from worker.dependencies import get_current_user, get_db_session
from worker.models import Worker
from worker.schemas import ApiResponse

from . import crud
from .config import get_remote_config
from .credentials import (
    RemoteConfigError,
    ensure_remote_credentials,
    is_admin_token_configured,
)
from .remote_client import RemoteShareClient, RemoteShareError
from .schemas import (
    CreateShareRequest,
    ShareTokenListItem,
    ShareTokenResponse,
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
    2. ensure_remote_credentials()：缺失凭据则调远端 auto-register;失败抛 RemoteConfigError(本接口返 503)
    3. 远端 quantcell.top 上传为 best-effort：
       - 成功 → short_url 写回,remote_status=UPLOADED
       - 失败 → remote_status=FAILED,remote_warning 反馈给前端
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

    # 3. 确保远端凭据已配置(若缺失则自动调远端 auto-register)
    user_id = current_user.get("user_id") or current_user.get("user_name") or "anonymous"
    try:
        ensure_remote_credentials(name=f"QuantCell-{user_id}", user_id=user_id)
    except RemoteConfigError as e:
        logger.error("create_share 自动配置远端凭据失败: %s", e)
        raise HTTPException(
            status_code=503,
            detail=f"远端分享凭据未配置且自动注册失败: {str(e)[:200]}",
        )

    # 4. 远端上传(失败 → 502,token 仍落库以便重试)
    short_url: Optional[str] = None
    remote_status = "PENDING"
    remote_warning: Optional[str] = None
    upload_failed: Optional[Exception] = None

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
            remote_status = "FAILED"
            remote_warning = f"远端上传失败:{str(e)[:200]}"
            upload_failed = e
            logger.warning("share 上传远端失败 id=%s err=%s", share.id, e)
        except Exception as e:  # noqa: BLE001  兜底避免上传异常影响主流程
            share.remote_status = "FAILED"
            share.remote_error = repr(e)[:500]
            remote_status = "FAILED"
            remote_warning = "远端上传异常"
            upload_failed = e
            logger.exception("share 上传远端异常 id=%s", share.id)
        finally:
            db.add(share)
            db.commit()
            db.refresh(share)

    # 5. 远端上传失败 → 返 502(token 已落库,可走列表点「重试」)
    if upload_failed is not None:
        raise HTTPException(
            status_code=502,
            detail=f"远端上传失败: {str(upload_failed)[:200]}",
        )

    # 6. 构造响应(永远只走远端,不再有 LOCAL_ONLY 兜底)
    response = ShareTokenResponse(
        id=share.id,
        token=plain_token,
        url=short_url or "",
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
    "/workers/{worker_id}/share/{share_id}/delete",
    response_model=ApiResponse,
    summary="物理删除分享 token",
)
def delete_share(
    worker_id: int,
    share_id: int,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
):
    """物理删除一个分享 token。仅 token 创建者可操作。

    与 revoke 的区别：
    - revoke：标记 revoked_at，记录保留在表中，便于审计
    - delete：从数据库彻底移除

    远端撤销为 best-effort：失败仅记录日志，不影响本地删除结果。
    """
    share = crud.get_share_by_id(db, share_id)
    if not share or share.worker_id != worker_id:
        raise HTTPException(status_code=404, detail="分享 token 不存在")

    # 权限：仅 token 创建者可删除
    user_id = current_user.get("user_id") or current_user.get("user_name")
    if share.created_by and user_id and share.created_by != user_id:
        raise HTTPException(status_code=403, detail="无权删除该分享")

    # 远端 best-effort 撤销（仅当已上传过且未撤销时）
    remote_revoked = False
    if share.remote_id and not share.is_revoked() and get_remote_config().is_ready:
        try:
            RemoteShareClient().revoke_sync(share.remote_id)
            remote_revoked = True
        except RemoteShareError as e:
            logger.warning("share 远端撤销失败(物理删除继续) id=%s err=%s", share.id, e)
        except Exception as e:  # noqa: BLE001
            logger.exception("share 远端撤销异常(物理删除继续) id=%s", share.id)

    # 本地物理删除
    crud.delete_share(db, share)

    return ApiResponse(data={
        "id": share_id,
        "deleted": True,
        "remote_revoked": remote_revoked,
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

    # 凭据未就绪时先自动配置(与 create_share 保持一致)
    user_id = current_user.get("user_id") or current_user.get("user_name") or "anonymous"
    try:
        ensure_remote_credentials(name=f"QuantCell-{user_id}", user_id=user_id)
    except RemoteConfigError as e:
        raise HTTPException(
            status_code=503,
            detail=f"远端分享凭据未配置且自动注册失败: {str(e)[:200]}",
        )

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
# 凭据管理端点(用于前端"一键启用远程分享模式"工作流)
# ============================================================
class GenerateCredentialsRequest(BaseModel):
    """生成凭据的请求体(可选 name)"""
    name: Optional[str] = Field(default=None, max_length=128)


@router.get(
    "/share/credentials/status",
    response_model=ApiResponse,
    summary="查询分享远端凭据状态",
)
def get_credentials_status(
    current_user: dict = Depends(get_current_user),
):
    """查询当前远端凭据配置状态(供 CLI / 运维使用)。

    Returns:
        ApiResponse.data 含:
        - ready: api_key AND hmac_secret 都已配置
        - has_api_key / has_hmac_secret: 是否已配置
        - base_url: 远端入口
        - admin_token_configured: 是否设置了 SHARE_REMOTE_ADMIN_TOKEN
    """
    from .credentials import is_admin_token_configured
    cfg = get_remote_config()
    return ApiResponse(data={
        "ready": cfg.is_ready,
        "has_api_key": bool(cfg.api_key),
        "has_hmac_secret": bool(cfg.hmac_secret),
        "base_url": cfg.base_url,
        "admin_token_configured": is_admin_token_configured(),
    })


@router.post(
    "/share/credentials/generate",
    response_model=ApiResponse,
    summary="一键生成并启用远程分享凭据(仅远端注册路径)",
)
def generate_credentials(
    payload: GenerateCredentialsRequest,
    current_user: dict = Depends(get_current_user),
):
    """一键生成 api_key + hmac_secret(仅远端注册路径)。

    流程:
    1. 读取 SHARE_REMOTE_ADMIN_TOKEN
       - 无值 → 返 503
    2. 调远端 POST /api/admin/devices/auto-register
       - 失败 → 返 502
    3. 凭据写入 config.local.toml + reload 单例
    4. 返回脱敏摘要(source 恒为 'remote')

    Returns:
        ApiResponse.data 含:
        - success: True
        - source: 'remote'
        - api_key_prefix: 仅前 8 位
        - ready: 热重载后 is_ready
        - base_url: 远端入口
    """
    user_id = current_user.get("user_id") or current_user.get("user_name") or "anonymous"
    name = payload.name or f"QuantCell-PC-{user_id}"

    if not is_admin_token_configured():
        raise HTTPException(
            status_code=503,
            detail="缺少 SHARE_REMOTE_ADMIN_TOKEN,无法自动注册远端凭据",
        )

    try:
        api_key, _hmac_secret = ensure_remote_credentials(name=name, user_id=user_id)
    except RemoteConfigError as e:
        raise HTTPException(status_code=502, detail=str(e)[:200])

    new_cfg = get_remote_config()
    return ApiResponse(data={
        "success": True,
        "source": "remote",
        "api_key_prefix": api_key[:8] + "…",
        "ready": new_cfg.is_ready,
        "base_url": new_cfg.base_url,
        "admin_token_configured": True,
    })


# 公开端点已删除(分享页完全走远端 quantcell.top,本地不再提供 GET /api/share/{token})
