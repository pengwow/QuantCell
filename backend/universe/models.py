"""标的池 ORM 模型（P2-03）。

三张表：
- universes：池主表，名称唯一，owner_id 记录创建者（语义同 P1-07 workers.owner_id）。
- universe_memberships：成分归属记录，included_from/until 表达成分历史，
  included_until 为 NULL 即当前在池成员，非 NULL 即历史成分（变更留痕）。
- universe_snapshots：成分快照，每次成员增删后写入变更后的完整成分 JSON，按时间回看。
"""

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text, func

from collector.db.database import Base


class Universe(Base):
    """标的池主表。"""

    __tablename__ = "universes"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    description = Column(String(500), nullable=True)
    owner_id = Column(Integer, nullable=True)  # 创建者用户 ID，单用户模式可空
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class UniverseMembership(Base):
    """成分归属记录：同一池内同一 symbol 同一时刻最多一条活跃记录。"""

    __tablename__ = "universe_memberships"

    id = Column(Integer, primary_key=True)
    universe_id = Column(Integer, ForeignKey("universes.id"), nullable=False)
    symbol = Column(String(50), nullable=False)
    included_from = Column(DateTime, nullable=False, server_default=func.now())
    included_until = Column(DateTime, nullable=True)  # NULL=当前成员

    __table_args__ = (Index("ix_universe_memberships_universe_symbol", "universe_id", "symbol"),)


class UniverseSnapshot(Base):
    """成分快照：每次成员增删后写入变更后的完整成分，按 created_at 回看。"""

    __tablename__ = "universe_snapshots"

    id = Column(Integer, primary_key=True)
    universe_id = Column(Integer, ForeignKey("universes.id"), nullable=False)
    symbols = Column(Text, nullable=False)  # JSON 数组字符串
    created_at = Column(DateTime, nullable=False, server_default=func.now())
