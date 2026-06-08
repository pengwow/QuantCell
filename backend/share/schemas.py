# -*- coding: utf-8 -*-
"""
Worker 分享系统 Pydantic Schema

严格区分：
- 受保护端点使用的完整信息（创建响应含明文 token，列表项不含）
- 公开端点使用的只读快照（白名单字段，绝不暴露敏感数据）
"""
from datetime import datetime
from typing import Any, List, Optional

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
    """创建分享 token 后的完整响应（含明文 token 与完整 URL）"""
    id: int
    token: str
    url: str                                       # 远端 short_url（如已上传）；否则为本地 fallback
    short_url: Optional[str] = None                # 显式的远端链接（本地分享时为 null）
    remote_status: str = "PENDING"                 # PENDING / UPLOADED / FAILED / LOCAL_ONLY
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


# ============================================================
# 公开端点（无需登录）
# ============================================================

class PositionSnapshot(BaseModel):
    """持仓概况（只读）—— 严格白名单字段，绝不包含杠杆、保证金、强平价等敏感信息"""
    symbol: str
    side: str
    quantity: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    pnl_percentage: float
    open_time: Optional[datetime] = None


class WorkerMetaSnapshot(BaseModel):
    """Worker 元信息（只读）"""
    id: int
    name: str
    status: str
    exchange: Optional[str] = None
    timeframe: Optional[str] = None
    market_type: Optional[str] = None
    trading_mode: Optional[str] = None
    symbols: List[str] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None


class ShareSnapshot(BaseModel):
    """公开分享页的完整 payload —— 严格白名单"""
    worker: WorkerMetaSnapshot
    metrics: Any  # 复用 stats_service.get_overview 的 metrics 结构
    cumulative_pnl_series: Any
    pnl_distribution: Any
    positions: List[PositionSnapshot] = Field(default_factory=list)
    generated_at: datetime
    read_only: bool = True
