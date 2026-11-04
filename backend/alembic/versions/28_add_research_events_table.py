"""新增 research_events：会话过程事件持久化表。

多 worker 部署时进程内事件缓冲只有持有 job 的进程可见，改为写库后
任一进程都能按自增 id（seq）增量读取。每个会话按 EVENTS_RETENTION 裁剪。

Revision ID: 28
Revises: 27
Create Date: 2026-11-04
"""

import sqlalchemy as sa

from alembic import op

revision = "28"
down_revision = "27"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    # 幂等：create_all 建过表的存量库直接跳过
    if _has_table("research_events"):
        return
    op.create_table(
        "research_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("research_sessions.id"), nullable=False),
        sa.Column("level", sa.String(length=8), nullable=False),
        sa.Column("stage", sa.String(length=48), nullable=False),
        sa.Column("msg", sa.Text(), nullable=False),
        sa.Column("ts", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_research_events_session_id", "research_events", ["session_id", "id"])


def downgrade() -> None:
    if _has_table("research_events"):
        op.drop_table("research_events")
