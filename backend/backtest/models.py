# -*- coding: utf-8 -*-
"""
回测模块数据库模型

提供回测任务和结果的数据库存储和管理功能。
"""

from datetime import datetime
from typing import Optional, Dict, Any, List

import sqlalchemy
from sqlalchemy import (
    Column, Integer, String, Text, DateTime,
    ForeignKey, Index, func
)
from sqlalchemy.orm import relationship

from collector.db.database import Base


class BacktestTask(Base):
    """回测任务SQLAlchemy模型

    对应backtest_tasks表的SQLAlchemy模型定义，用于存储回测任务信息
    """
    __tablename__ = "backtest_tasks"

    id = Column(String, primary_key=True, index=True)  # 任务唯一标识
    strategy_name = Column(String, nullable=False, index=True)  # 策略名称
    backtest_config = Column(Text, nullable=False)  # JSON格式，回测配置
    status = Column(String, nullable=False, default="pending", index=True)  # 任务状态: pending/running/completed/failed
    created_at = Column(DateTime, server_default=func.now(), index=True)  # 创建时间
    started_at = Column(DateTime, nullable=True)  # 开始执行时间
    completed_at = Column(DateTime, nullable=True)  # 完成时间
    result_id = Column(String, nullable=True)  # 关联的回测结果ID

    # 关联关系
    results = relationship("BacktestResult", back_populates="task", cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_backtest_tasks_status', 'status'),
        Index('idx_backtest_tasks_strategy', 'strategy_name'),
        Index('idx_backtest_tasks_created', 'created_at'),
    )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'id': self.id,
            'strategy_name': self.strategy_name,
            'backtest_config': self.backtest_config,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'result_id': self.result_id,
        }


class BacktestResult(Base):
    """回测结果SQLAlchemy模型

    对应backtest_results表的SQLAlchemy模型定义，用于存储回测结果信息
    """
    __tablename__ = "backtest_results"

    id = Column(String, primary_key=True, index=True)  # 结果唯一标识
    task_id = Column(String, ForeignKey('backtest_tasks.id'), nullable=False, index=True)  # 关联的回测任务ID
    task = relationship("BacktestTask", back_populates="results")

    strategy_name = Column(String, nullable=False, index=True)  # 策略名称
    symbol = Column(String, nullable=False, index=True)  # 货币对标识
    metrics = Column(Text, nullable=False)  # JSON格式，包含翻译后的指标
    trades = Column(Text, nullable=False)  # JSON格式，交易记录
    equity_curve = Column(Text, nullable=False)  # JSON格式，资金曲线
    strategy_data = Column(Text, nullable=False)  # JSON格式，策略数据
    created_at = Column(DateTime, server_default=func.now(), index=True)  # 创建时间

    __table_args__ = (
        Index('idx_backtest_results_task', 'task_id'),
        Index('idx_backtest_results_strategy', 'strategy_name'),
        Index('idx_backtest_results_symbol', 'symbol'),
    )

    def get_metrics_dict(self) -> Dict[str, Any]:
        """获取指标字典"""
        import json
        try:
            return json.loads(self.metrics) if self.metrics else {}
        except json.JSONDecodeError:
            return {}

    def get_trades_list(self) -> List[Dict[str, Any]]:
        """获取交易列表"""
        import json
        try:
            return json.loads(self.trades) if self.trades else []
        except json.JSONDecodeError:
            return []

    def get_equity_curve_list(self) -> List[Dict[str, Any]]:
        """获取资金曲线列表"""
        import json
        try:
            return json.loads(self.equity_curve) if self.equity_curve else []
        except json.JSONDecodeError:
            return []

    def get_strategy_data_dict(self) -> Dict[str, Any]:
        """获取策略数据字典"""
        import json
        try:
            return json.loads(self.strategy_data) if self.strategy_data else {}
        except json.JSONDecodeError:
            return {}

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'id': self.id,
            'task_id': self.task_id,
            'strategy_name': self.strategy_name,
            'symbol': self.symbol,
            'metrics': self.get_metrics_dict(),
            'trades': self.get_trades_list(),
            'equity_curve': self.get_equity_curve_list(),
            'strategy_data': self.get_strategy_data_dict(),
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
