"""
回测模块数据库模型

提供回测任务和结果的数据库存储和管理功能。
"""

from typing import Any

from sqlalchemy import Column, DateTime, Index, String, Text, func

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

    __table_args__ = (
        Index("idx_backtest_tasks_status", "status"),
        Index("idx_backtest_tasks_strategy", "strategy_name"),
        Index("idx_backtest_tasks_created", "created_at"),
    )

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "strategy_name": self.strategy_name,
            "backtest_config": self.backtest_config,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "result_id": self.result_id,
        }
