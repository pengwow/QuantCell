"""add_share_tokens

为 Worker 详情页的分享系统新增 share_tokens 与 share_views 表。

Revision ID: 16
Revises: 15
Create Date: 2026-06-06 23:00:00.000000

"""

from typing import TYPE_CHECKING

import sqlalchemy as sa

from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "16"
down_revision: str | Sequence[str] | None = "15"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """创建 share_tokens 与 share_views 表"""
    op.create_table(
        "share_tokens",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("worker_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("token_prefix", sa.String(length=8), nullable=False),
        sa.Column("one_time", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("max_views", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("view_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.ForeignKeyConstraint(["worker_id"], ["workers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="idx_share_tokens_hash"),
    )
    op.create_index("idx_share_tokens_worker", "share_tokens", ["worker_id"], unique=False)

    op.create_table(
        "share_views",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("token_id", sa.Integer(), nullable=False),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column(
            "viewed_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.ForeignKeyConstraint(["token_id"], ["share_tokens.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_share_views_token", "share_views", ["token_id"], unique=False)
    op.create_index("idx_share_views_ip_time", "share_views", ["ip", "viewed_at"], unique=False)


def downgrade() -> None:
    """回滚：删除两张表"""
    op.drop_index("idx_share_views_ip_time", table_name="share_views")
    op.drop_index("idx_share_views_token", table_name="share_views")
    op.drop_table("share_views")
    op.drop_index("idx_share_tokens_worker", table_name="share_tokens")
    op.drop_table("share_tokens")
