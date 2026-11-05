"""research_trials 增加 replay_meta_json（P2 回放元数据）。

回放产生新 trial 并通过既有 replay_of_id 关联原记录；本列存
{partial, missing, notes, tolerance, diff, consistent, unreproducible}，
让页面在刷新后仍能展示「部分复现」原因与差异阈值。

Revision ID: 29
Revises: 28
Create Date: 2026-11-05
"""

import sqlalchemy as sa

from alembic import op

revision = "29"
down_revision = "28"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    try:
        return {col["name"] for col in inspector.get_columns(table)}
    except sa.exc.NoSuchTableError:
        return set()


def upgrade() -> None:
    # 幂等：create_all 建过表的存量库直接跳过
    if "replay_meta_json" not in _columns("research_trials"):
        op.add_column("research_trials", sa.Column("replay_meta_json", sa.Text(), nullable=True))


def downgrade() -> None:
    if "replay_meta_json" in _columns("research_trials"):
        op.drop_column("research_trials", "replay_meta_json")
