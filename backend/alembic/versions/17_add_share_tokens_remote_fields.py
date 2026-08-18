"""add_share_tokens_remote_fields

为 share_tokens 表新增远端分发（quantcell.top）相关字段：
- remote_id: quantcell.top 分配的远端 id
- short_url: 公开短链（https://share.quantcell.top/<token>）
- remote_status: 远端推送状态（PENDING / UPLOADED / FAILED / REVOKED）
- remote_error: 推送失败时的脱敏错误信息

Revision ID: 17
Revises: 16
Create Date: 2026-06-08 19:50:00.000000

"""

from typing import TYPE_CHECKING

import sqlalchemy as sa

from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "17"
down_revision: str | Sequence[str] | None = "16"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """为 share_tokens 表追加远端分发相关列"""
    # remote_id：远端主键；空字符串与 None 视为未上传
    op.add_column(
        "share_tokens",
        sa.Column("remote_id", sa.String(length=64), nullable=True),
    )
    op.create_index("idx_share_tokens_remote_id", "share_tokens", ["remote_id"], unique=False)

    # short_url：返回给前端的公开短链
    op.add_column(
        "share_tokens",
        sa.Column("short_url", sa.String(length=512), nullable=True),
    )

    # remote_status：远端推送状态枚举；默认 PENDING
    op.add_column(
        "share_tokens",
        sa.Column(
            "remote_status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'PENDING'"),
        ),
    )

    # remote_error：失败时记录（脱敏后）
    op.add_column(
        "share_tokens",
        sa.Column("remote_error", sa.String(length=512), nullable=True),
    )


def downgrade() -> None:
    """回滚：删除远端分发相关列"""
    op.drop_column("share_tokens", "remote_error")
    op.drop_column("share_tokens", "remote_status")
    op.drop_column("share_tokens", "short_url")
    op.drop_index("idx_share_tokens_remote_id", table_name="share_tokens")
    op.drop_column("share_tokens", "remote_id")
