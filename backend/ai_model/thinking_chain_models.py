"""思维链数据模型

定义 ThinkingChain SQLAlchemy 模型，用于存储 AI 思维链配置
"""
import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import Boolean, Column, DateTime, Enum, Integer, String, Text, func, Index
from sqlalchemy.orm import declarative_base

# 创建独立的 Base 避免循环导入
Base = declarative_base()


class ThinkingChainType(str, Enum):
    """思维链类型枚举"""
    STRATEGY_GENERATION = "strategy_generation"
    INDICATOR_GENERATION = "indicator_generation"


class ThinkingChain(Base):
    """思维链 SQLAlchemy 模型

    对应 thinking_chains 表的 SQLAlchemy 模型定义
    用于存储 AI 思维链配置
    """
    __tablename__ = "thinking_chains"

    # 主键 ID，使用 UUID
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), index=True)

    # 思维链类型：策略生成 / 指标生成
    chain_type = Column(String(50), nullable=False, index=True)

    # 思维链名称
    name = Column(String(255), nullable=False)

    # 思维链描述
    description = Column(Text, nullable=True)

    # 思维链步骤，JSON 格式存储
    steps = Column(Text, nullable=False)

    # 是否激活
    is_active = Column(Boolean, default=True, index=True)

    # 创建时间
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    # 更新时间
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    # 添加索引优化查询性能
    __table_args__ = (
        # 联合索引：类型 + 是否激活，用于查询激活的思维链
        Index('idx_thinking_chain_type_active', 'chain_type', 'is_active'),
        # 联合索引：类型 + 创建时间，用于分页查询
        Index('idx_thinking_chain_type_created', 'chain_type', 'created_at'),
    )

    def to_dict(self) -> Dict[str, Any]:
        """将模型转换为字典

        Returns:
            Dict[str, Any]: 模型数据字典
        """
        return {
            "id": self.id,
            "chain_type": self.chain_type,
            "name": self.name,
            "description": self.description,
            "steps": self.get_steps(),
            "is_active": self.is_active,
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

    def set_steps(self, steps: List[Dict[str, Any]]) -> None:
        """设置思维链步骤

        Args:
            steps: 思维链步骤列表
        """
        self.steps = json.dumps(steps, ensure_ascii=False) if steps else json.dumps([])

    def get_steps(self) -> List[Dict[str, Any]]:
        """获取思维链步骤

        Returns:
            List[Dict[str, Any]]: 思维链步骤列表
        """
        if self.steps:
            return json.loads(self.steps)
        return []
