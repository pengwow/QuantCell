# -*- coding: utf-8 -*-
"""
策略模块数据库模型

提供策略的数据库存储和管理功能。
"""

from datetime import datetime
from typing import Optional, Dict, Any, List

from sqlalchemy import (
    Column, Integer, String, Text, Float, Boolean, DateTime,
    ForeignKey, Index, UniqueConstraint, func
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

    # 策略版本和元数据
    version = Column(String(20), default="1.0.0")
    tags = Column(Text, nullable=True)  # JSON 格式的标签列表

    # 策略代码 (兼容 collector.db.models 的 content 字段)
    code = Column(Text, nullable=True)

    # 策略参数 (JSON格式，兼容 collector.db.models 的 parameters 字段)
    parameters = Column(Text, nullable=True)

    # 策略类型: default, legacy
    strategy_type = Column(String(20), default="default")

    # 状态: active, inactive, deprecated
    status = Column(String(20), default="active")

    # 时间戳
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # 关联关系
    parameters = relationship("StrategyParameter", back_populates="strategy", cascade="all, delete-orphan")
    # workers 关系由 Worker 模型中的 relationship 使用 backref 自动创建

    __table_args__ = (
        Index('idx_strategy_name', 'name'),
        Index('idx_strategy_status', 'status'),
        Index('idx_strategy_type', 'strategy_type'),
    )

    def get_tags_list(self) -> List[str]:
        """获取标签列表"""
        import json
        try:
            return json.loads(self.tags) if self.tags else []
        except json.JSONDecodeError:
            return []

    def set_tags_list(self, tags: List[str]):
        """设置标签列表"""
        import json
        self.tags = json.dumps(tags)

    def get_parameters_list(self) -> List[Dict[str, Any]]:
        """获取参数列表"""
        import json
        try:
            return json.loads(self.parameters) if self.parameters else []
        except json.JSONDecodeError:
            return []

    def set_parameters_list(self, params: List[Dict[str, Any]]):
        """设置参数列表"""
        import json
        self.parameters = json.dumps(params)

    @property
    def content(self) -> Optional[str]:
        """兼容 collector.db.models 的 content 属性"""
        return self.code

    @content.setter
    def content(self, value: Optional[str]):
        """兼容 collector.db.models 的 content 属性"""
        self.code = value

    @property
    def filename(self) -> Optional[str]:
        """兼容 collector.db.models 的 filename 属性"""
        return self.file_name

    @filename.setter
    def filename(self, value: Optional[str]):
        """兼容 collector.db.models 的 filename 属性"""
        self.file_name = value

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'file_path': self.file_path,
            'file_name': self.file_name,
            'version': self.version,
            'tags': self.get_tags_list(),
            'strategy_type': self.strategy_type,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class StrategyParameter(Base):
    """策略参数模型"""
    __tablename__ = "strategy_parameters"

    id = Column(Integer, primary_key=True, index=True)
    strategy_id = Column(Integer, ForeignKey('strategies.id'), nullable=False, index=True)
    strategy = relationship("Strategy", back_populates="parameters")

    # 参数信息
    param_name = Column(String(100), nullable=False)
    param_type = Column(String(20), default='string')  # string, int, float, bool, json
    default_value = Column(Text, nullable=True)
    description = Column(Text, nullable=True)

    # 参数范围
    min_value = Column(Float, nullable=True)
    max_value = Column(Float, nullable=True)

    # 是否必填
    required = Column(Boolean, default=False)

    # 时间戳
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint('strategy_id', 'param_name', name='unique_strategy_parameter'),
        Index('idx_strategy_parameter', 'strategy_id', 'param_name'),
    )

    def get_default_value(self) -> Any:
        """获取默认值"""
        import json
        try:
            if self.param_type == 'int':
                return int(self.default_value) if self.default_value else 0
            elif self.param_type == 'float':
                return float(self.default_value) if self.default_value else 0.0
            elif self.param_type == 'bool':
                return self.default_value.lower() in ('true', '1', 'yes', 'on') if self.default_value else False
            elif self.param_type == 'json':
                return json.loads(self.default_value) if self.default_value else {}
            else:
                return self.default_value or ''
        except (ValueError, json.JSONDecodeError):
            return self.default_value

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'id': self.id,
            'strategy_id': self.strategy_id,
            'param_name': self.param_name,
            'param_type': self.param_type,
            'default_value': self.get_default_value(),
            'description': self.description,
            'min_value': self.min_value,
            'max_value': self.max_value,
            'required': self.required,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
