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
    factors = Column(Text, nullable=True)
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

    def get_factors_list(self) -> list[dict[str, Any]]:
        try:
            return json.loads(self.factors) if self.factors else []
        except json.JSONDecodeError:
            return []

    def set_factors_list(self, factors: list[dict[str, Any]]):
        self.factors = json.dumps(factors)


class StrategyVersion(Base):
    """策略版本快照（只在真正走保存入口时写入，见 service._record_version_snapshot）。

    与 strategies.version 的区别：那一列是策略文件里声明的单个版本号，不是历史；
    本表按保存动作留快照，去重规则写在写入侧（code_hash 与上一条相同则跳过），
    所以不加唯一约束——同一内容在不同时刻可能被合法重存（历史只留首条）。
    """

    __tablename__ = "strategy_versions"

    id = Column(Integer, primary_key=True, index=True)
    strategy_name = Column(String(100), nullable=False)
    # 策略文件里声明的版本号（__version__ / VERSION 常量）；文件没声明就是 None
    version = Column(String(20), nullable=True)
    # 完整快照的 sha256（去重依据；列表接口只回前 8 位给前端展示）
    code_hash = Column(String(64), nullable=False)
    code = Column(Text, nullable=False)
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        Index("idx_strategy_version_name", "strategy_name"),
        Index("idx_strategy_version_created", "created_at"),
    )
