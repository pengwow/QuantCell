"""indicator_alert_rules.period 列改名 interval（vocab P2-10：K线周期统一 interval 词汇）

应用面 ORM 属性早已是 interval（Column("period") 显式映射），本迁移把主库的
物理列名一并对齐，消除最后一个历史列名例外。collector 自有库（features.freq /
indicator_alert_rules.period）由 collector/db/migrations.py 的
rename_kline_interval_columns 负责改名。

Revision ID: 46
Revises: 45
Create Date: 2026-11-17
"""

import sqlalchemy as sa

from alembic import op

revision = "46"
down_revision = "45"
branch_labels = None
depends_on = None

_TABLE = "indicator_alert_rules"
_LEGACY = "period"
_NEW = "interval"


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if _TABLE not in inspector.get_table_names():
        return
    columns = {c["name"] for c in inspector.get_columns(_TABLE)}
    if _LEGACY not in columns:
        return  # 已改名或新库直建 interval，幂等跳过
    # SQLite(>=3.25)/PG 均支持 RENAME COLUMN；interval 非两库保留字
    op.execute(f'ALTER TABLE {_TABLE} RENAME COLUMN {_LEGACY} TO "{_NEW}"')


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if _TABLE not in inspector.get_table_names():
        return
    columns = {c["name"] for c in inspector.get_columns(_TABLE)}
    if _NEW not in columns:
        return
    op.execute(f'ALTER TABLE {_TABLE} RENAME COLUMN {_NEW} TO "{_LEGACY}"')
