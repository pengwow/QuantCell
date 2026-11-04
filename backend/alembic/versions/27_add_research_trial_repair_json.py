"""research_trials 增加 repair_json（自修复内环的每轮摘要）。

代码生成/评估失败时把错误分类后回灌 LLM 重写，最多 repair_rounds 轮；
每轮只落 {round, kind, error摘要}，便于复盘，不塞入完整报错原文。

Revision ID: 27
Revises: 26
Create Date: 2026-11-04
"""

import sqlalchemy as sa

from alembic import op

revision = "27"
down_revision = "26"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    try:
        return {col["name"] for col in inspector.get_columns(table)}
    except sa.exc.NoSuchTableError:
        return set()


def upgrade() -> None:
    if "repair_json" not in _columns("research_trials"):
        op.add_column("research_trials", sa.Column("repair_json", sa.Text(), nullable=True))


def downgrade() -> None:
    if "repair_json" in _columns("research_trials"):
        op.drop_column("research_trials", "repair_json")
