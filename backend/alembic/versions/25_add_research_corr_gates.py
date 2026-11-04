"""research_trials 增加硬门 3 的实测相关性列。

评估完成时把 corr_sota / corr_library 落库，续跑（status=evaluated）时 judge
直接读这两个列，不需要重新评估；列缺失（历史数据）时 judge 记为 unknown 而非放行。

Revision ID: 25
Revises: 24
Create Date: 2026-11-04
"""

import sqlalchemy as sa

from alembic import op

revision = "25"
down_revision = "24"
branch_labels = None
depends_on = None


# 与 22/23 号迁移同理：create_all 抢先建表（25 版结构、列已存在）的库直接跳过
def _columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    try:
        return {col["name"] for col in inspector.get_columns(table)}
    except sa.exc.NoSuchTableError:
        return set()


def _add_column_if_missing(table: str, column: sa.Column) -> None:
    if column.name not in _columns(table):
        op.add_column(table, column)


def upgrade() -> None:
    _add_column_if_missing("research_trials", sa.Column("corr_sota", sa.Float(), nullable=True))
    _add_column_if_missing("research_trials", sa.Column("corr_library", sa.Float(), nullable=True))


def downgrade() -> None:
    cols = _columns("research_trials")
    if "corr_library" in cols:
        op.drop_column("research_trials", "corr_library")
    if "corr_sota" in cols:
        op.drop_column("research_trials", "corr_sota")
