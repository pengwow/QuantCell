"""add_round_trip_id_to_worker_trades

为 worker_trades 表添加 round_trip_id 列（round-trip 组键，paper 落库回填）
与索引，对应 WorkerTrade.round_trip_id 模型列。
存量行保持 NULL = 未配对，分组视图按行自成一组展示。

Revision ID: 21
Revises: 20
Create Date: 2026-10-29 00:00:00.000000
"""

from typing import TYPE_CHECKING

import sqlalchemy as sa

from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "21"
down_revision: str | Sequence[str] | None = "20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """新增 round_trip_id 列 + 组键索引"""
    with op.batch_alter_table("worker_trades", schema=None) as batch_op:
        batch_op.add_column(sa.Column("round_trip_id", sa.String(length=100), nullable=True))
        batch_op.create_index("idx_worker_trades_round_trip", ["round_trip_id"], unique=False)


def downgrade() -> None:
    """回滚：删索引 + 删列"""
    with op.batch_alter_table("worker_trades", schema=None) as batch_op:
        batch_op.drop_index("idx_worker_trades_round_trip")
        batch_op.drop_column("round_trip_id")
