"""因子档案与分析快照的数据库模型。

表达式真相源仍是 factor.engine 内置常量 + data/factor/custom_factors.json；
本表只存元数据/指标/生命周期等派生档案，按 name 关联，不参与因子求值。
"""

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, Text, func

from collector.db.database import Base


class FactorCatalog(Base):
    """因子档案：一因子一行（内置 + 自定义）。"""

    __tablename__ = "factor_catalog"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True, index=True)
    label = Column(String(200), nullable=True)
    category = Column(String(50), nullable=True)
    expression = Column(Text, nullable=True)
    is_builtin = Column(Boolean, nullable=False, default=False)
    supported = Column(Boolean, nullable=False, default=True)
    lifecycle_status = Column(String(20), nullable=False, default="DISCOVERED")
    last_metrics = Column(Text, nullable=True)  # 最近快照核心指标 JSON 摘要
    last_snapshot_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (Index("idx_factor_catalog_status", "lifecycle_status"),)


class FactorSnapshot(Base):
    """因子分析快照：参数 + 完整指标 JSON + parquet 因子值文件引用。"""

    __tablename__ = "factor_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    factor_name = Column(String(100), nullable=False, index=True)
    params_json = Column(Text, nullable=False)
    metrics_json = Column(Text, nullable=False)
    bar_count = Column(Integer, nullable=False, default=0)
    snapshot_file = Column(String(500), nullable=True)  # 相对 backend 的 posix 路径
    created_at = Column(DateTime, server_default=func.now(), index=True)
