"""策略模块数据库模型"""

import json
from typing import Any

from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import relationship

from collector.db.database import Base


class Strategy(Base):
    """策略模型"""

    __tablename__ = "strategies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    file_path = Column(String(500), nullable=True)
    file_name = Column(String(200), nullable=True)
    version = Column(String(20), default="1.0.0")
    tags = Column(Text, nullable=True)
    code = Column(Text, nullable=True)
    parameters = Column(Text, nullable=True)
    strategy_type = Column(String(20), default="rule")
    status = Column(String(20), default="active")
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # 关联关系
    workers = relationship("Worker", back_populates="strategy", lazy="dynamic")

    __table_args__ = (
        Index("idx_strategy_name", "name"),
        Index("idx_strategy_status", "status"),
    )

    def get_tags_list(self) -> list[str]:
        try:
            return json.loads(self.tags) if self.tags else []
        except json.JSONDecodeError:
            return []

    def set_tags_list(self, tags: list[str]):
        self.tags = json.dumps(tags)

    def get_parameters_list(self) -> list[dict[str, Any]]:
        try:
            return json.loads(self.parameters) if self.parameters else []
        except json.JSONDecodeError:
            return []

    def set_parameters_list(self, params: list[dict[str, Any]]):
        self.parameters = json.dumps(params)
