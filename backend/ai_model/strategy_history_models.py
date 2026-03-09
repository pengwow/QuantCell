"""策略历史记录模型

定义 StrategyHistory SQLAlchemy 模型，用于存储 AI 生成策略的历史记录
"""
import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import sqlalchemy
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text, func, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base

# 创建独立的 Base 避免循环导入
Base = declarative_base()


class StrategyHistory(Base):
    """策略历史记录 SQLAlchemy 模型

    对应 strategy_history 表的 SQLAlchemy 模型定义
    用于存储 AI 生成策略的历史记录
    """
    __tablename__ = "strategy_history"

    # 主键 ID，使用 UUID
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), index=True)

    # 用户 ID，关联用户表
    user_id = Column(String(255), nullable=False, index=True)

    # 策略标题
    title = Column(String(255), nullable=False)

    # 用户需求描述
    requirement = Column(Text, nullable=False)

    # 生成的策略代码
    code = Column(Text, nullable=False)

    # 策略解释说明
    explanation = Column(Text, nullable=True)

    # 使用的 AI 模型 ID
    model_id = Column(String(255), nullable=True)

    # 温度参数
    temperature = Column(Float, nullable=True, default=0.7)

    # 使用的 Token 数量，JSON 格式存储
    tokens_used = Column(Text, nullable=True)

    # 生成耗时（秒）
    generation_time = Column(Float, nullable=True)

    # 代码是否有效
    is_valid = Column(Boolean, default=True, index=True)

    # 标签，JSON 格式存储
    tags = Column(Text, nullable=True)

    # 创建时间
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    # 更新时间
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    # 添加索引优化查询性能
    __table_args__ = (
        # 联合索引：用户ID + 创建时间，用于分页查询
        Index('idx_strategy_history_user_created', 'user_id', 'created_at'),
        # 联合索引：用户ID + 是否有效
        Index('idx_strategy_history_user_valid', 'user_id', 'is_valid'),
    )

    def to_dict(self) -> Dict[str, Any]:
        """将模型转换为字典

        Returns:
            Dict[str, Any]: 模型数据字典
        """
        return {
            "id": self.id,
            "user_id": self.user_id,
            "title": self.title,
            "requirement": self.requirement,
            "code": self.code,
            "explanation": self.explanation,
            "model_id": self.model_id,
            "temperature": self.temperature,
            "tokens_used": json.loads(self.tokens_used) if self.tokens_used else None,
            "generation_time": self.generation_time,
            "is_valid": self.is_valid,
            "tags": json.loads(self.tags) if self.tags else [],
            "created_at": self._format_datetime(self.created_at),
            "updated_at": self._format_datetime(self.updated_at),
        }

    @staticmethod
    def _format_datetime(dt: Optional[datetime]) -> Optional[str]:
        """格式化 datetime 对象为字符串

        Args:
            dt: datetime 对象

        Returns:
            Optional[str]: 格式化后的字符串
        """
        if dt is None:
            return None
        return dt.strftime("%Y-%m-%d %H:%M:%S")

    def set_tokens_used(self, tokens: Dict[str, Any]) -> None:
        """设置 Token 使用量

        Args:
            tokens: Token 使用量字典
        """
        self.tokens_used = json.dumps(tokens) if tokens else None

    def set_tags(self, tags: List[str]) -> None:
        """设置标签

        Args:
            tags: 标签列表
        """
        self.tags = json.dumps(tags) if tags else None

    def get_tokens_used(self) -> Optional[Dict[str, Any]]:
        """获取 Token 使用量

        Returns:
            Optional[Dict[str, Any]]: Token 使用量字典
        """
        if self.tokens_used:
            return json.loads(self.tokens_used)
        return None

    def get_tags(self) -> List[str]:
        """获取标签列表

        Returns:
            List[str]: 标签列表
        """
        if self.tags:
            return json.loads(self.tags)
        return []
