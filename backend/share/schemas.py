# -*- coding: utf-8 -*-
"""
Worker 分享系统 Pydantic Schema

仅保留受保护端点使用的 schema（创建响应含明文 token，列表项不含）。

说明：
- 公开只读页已下线，分享功能完全走 quantcell.top 远端分发
- 本地不再提供 GET /api/share/{token} 端点，因此 PositionSnapshot /
  WorkerMetaSnapshot / ShareSnapshot 等"白名单只读快照"已不再使用
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ============================================================
# 受保护端点（需要登录）
# ============================================================

class CreateShareRequest(BaseModel):
    """创建分享 token 的请求体"""
    expires_in_seconds: Optional[int] = Field(
        default=None,
        ge=0,
        description="过期时间（秒），0 或 null 表示不限时"
    )
    one_time: bool = Field(
        default=False,
        description="是否一次性访问（访问一次后立即失效）"
    )
    max_views: Optional[int] = Field(
        default=None,
        ge=1,
        description="最大访问次数，null 表示不限"
    )

    @field_validator("expires_in_seconds")
    @classmethod
    def _validate_expires(cls, v: Optional[int]) -> Optional[int]:
        """expires_in_seconds 为 0 时统一转为 None（不限时）"""
        if v is None or v == 0:
            return None
        # 最长 90 天
        if v > 90 * 24 * 3600:
            raise ValueError("expires_in_seconds 不能超过 90 天")
        return v


class ShareTokenResponse(BaseModel):
    """创建分享 token 后的完整响应（含明文 token 与远端链接）

    远端上传失败时：short_url 仍可能为 None（远端未接受），
    remote_status='FAILED',remote_warning 反馈给前端。
    """
    id: int
    token: str
    url: str                                       # 远端 short_url；未上传/失败时为 ''
    short_url: Optional[str] = None                # 显式的远端链接
    remote_status: str = "PENDING"                 # PENDING / UPLOADED / FAILED / REVOKED
    remote_warning: Optional[str] = None          # 远端上传失败时的非阻塞提示
    expires_at: Optional[datetime]
    one_time: bool
    max_views: Optional[int]
    created_at: datetime
    created_by: Optional[str] = None


class ShareTokenListItem(BaseModel):
    """分享 token 列表项（不含明文 token，仅显示 prefix）"""
    id: int
    worker_id: int
    token_prefix: str
    one_time: bool
    max_views: Optional[int]
    view_count: int
    created_at: datetime
    expires_at: Optional[datetime]
    revoked: bool
    revoked_at: Optional[datetime] = None
    created_by: Optional[str] = None
    # 远端字段
    short_url: Optional[str] = None
    remote_status: str = "PENDING"
    remote_error: Optional[str] = None
