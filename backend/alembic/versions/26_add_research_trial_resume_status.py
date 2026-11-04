"""research_trials 增加 resume_status（中断续跑定位用）。

暂停/取消/预算耗尽时把在飞 trial 标为 interrupted（终态），中断前所处
step 记入 resume_status，恢复时据此接续，避免永久 running/coded。

Revision ID: 26
Revises: 25
Create Date: 2026-11-04
"""

import sqlalchemy as sa

from alembic import op

revision = "26"
down_revision = "25"
branch_labels = None
depends_on = None


# 与 22/23/25 同理：create_all 抢先建表时列已存在，直接跳过
def _columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    try:
        return {col["name"] for col in inspector.get_columns(table)}
    except sa.exc.NoSuchTableError:
        return set()


def upgrade() -> None:
    if "resume_status" not in _columns("research_trials"):
        op.add_column("research_trials", sa.Column("resume_status", sa.String(length=16), nullable=True))


def downgrade() -> None:
    if "resume_status" in _columns("research_trials"):
        op.drop_column("research_trials", "resume_status")
