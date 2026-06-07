# -*- coding: utf-8 -*-
"""
Worker 分享系统数据模型

- ShareToken: 分享 token 元数据
- ShareView:  分享查看记录（用于审计与限速）
"""
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import relationship

from collector.db.database import Base


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

    worker = relationship("Worker", lazy="select")
    views = relationship("ShareView", back_populates="token", cascade="all, delete-orphan")

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
        """token 是否仍处于有效状态（可访问）"""
        if self.is_revoked():
            return False
        if self.is_expired(now):
            return False
        if self.is_one_time_consumed():
            return False
        if self.has_reached_max_views():
            return False
        return True


class ShareView(Base):
    """分享查看记录

    每次公开端点被访问时记录一行（无论 token 是否有效），
    用于审计、防滥用、限速。
    """
    __tablename__ = "share_views"

    id = Column(Integer, primary_key=True, index=True)
    token_id = Column(Integer, ForeignKey("share_tokens.id", ondelete="CASCADE"), nullable=False)
    ip = Column(String(64), nullable=True)
    user_agent = Column(Text, nullable=True)
    viewed_at = Column(DateTime, default=func.now(), nullable=False)
    success = Column(Boolean, default=True, nullable=False)

    token = relationship("ShareToken", back_populates="views", lazy="select")

    __table_args__ = (
        Index("idx_share_views_token", "token_id"),
        Index("idx_share_views_ip_time", "ip", "viewed_at"),
    )
