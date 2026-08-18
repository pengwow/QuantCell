"""
Worker 分享系统数据模型

- ShareToken: 分享 token 元数据

说明：
- 公开只读页已下线，分享功能完全走 quantcell.top 远端分发
- 本地不再维护 ShareView 访问审计（远端 quantcell.top 端负责统计）
"""

from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)

from collector.db.database import Base

if TYPE_CHECKING:
    from datetime import datetime


class ShareToken(Base):
    """分享 token 元数据

    token 字段仅保存 SHA256 哈希值（64 hex chars），明文只在创建时返回给调用方一次。
    token_prefix 保存前 8 位明文用于列表展示（无安全风险）。
    """

    __tablename__ = "share_tokens"

    id = Column(Integer, primary_key=True, index=True)
    worker_id = Column(Integer, ForeignKey("workers.id", ondelete="CASCADE"), nullable=False)
    token_hash = Column(String(64), nullable=False, unique=True)
    token_prefix = Column(String(8), nullable=False)

    # 控制选项
    one_time = Column(Boolean, default=False, nullable=False)
    max_views = Column(Integer, nullable=True)  # null 表示不限

    # 审计
    created_by = Column(String(64), nullable=True)  # 创建者 user_id，未登录时为 anonymous
    created_at = Column(DateTime, default=func.now(), nullable=False)
    expires_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)

    # 计数
    view_count = Column(Integer, default=0, nullable=False)

    # 远端分发（quantcell.top）—— 字段可空以兼容旧记录
    remote_id = Column(String(64), nullable=True, index=True)  # quantcell.top 分配
    short_url = Column(String(512), nullable=True)  # e.g. https://share.quantcell.top/<token>
    remote_status = Column(String(16), default="PENDING", nullable=False)  # PENDING/UPLOADED/FAILED/REVOKED
    remote_error = Column(String(512), nullable=True)  # 上传失败时的错误信息（脱敏）

    __table_args__ = (
        Index("idx_share_tokens_worker", "worker_id"),
        Index("idx_share_tokens_hash", "token_hash", unique=True),
    )

    def is_expired(self, now: datetime) -> bool:
        """是否已过期"""
        if self.expires_at is None:
            return False
        return now >= self.expires_at

    def is_revoked(self) -> bool:
        """是否已撤销"""
        return self.revoked_at is not None

    def is_one_time_consumed(self) -> bool:
        """一次性 token 是否已被消费"""
        return self.one_time and self.view_count > 0

    def has_reached_max_views(self) -> bool:
        """是否达到最大访问次数"""
        if self.max_views is None:
            return False
        return self.view_count >= self.max_views

    def is_active(self, now: datetime) -> bool:
        """token 是否仍处于有效状态（可访问）

        注：仅用于本地一致性检查，公开访问入口已下线。
        """
        if self.is_revoked():
            return False
        if self.is_expired(now):
            return False
        if self.is_one_time_consumed():
            return False
        return not self.has_reached_max_views()
