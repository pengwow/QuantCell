"""add_margin_used_to_worker_positions

为 worker_positions 表添加 margin_used 字段，对应 WorkerPosition.margin_used 模型列。
后端 crud.get_worker_positions_filtered 在 SELECT 阶段引用该列，
旧表未包含该列会导致 sqlite3.OperationalError: no such column: worker_positions.margin_used。

Revision ID: 15
Revises: 14
Create Date: 2026-06-06 22:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '15'
down_revision: Union[str, Sequence[str], None] = '14'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """为 worker_positions 表添加 margin_used 列"""
    # 使用 IF NOT EXISTS 模式兼容 SQLite 多次执行
    with op.batch_alter_table('worker_positions', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('margin_used', sa.Float(), nullable=True, server_default='0.0')
        )


def downgrade() -> None:
    """回滚：移除 margin_used 列"""
    with op.batch_alter_table('worker_positions', schema=None) as batch_op:
        batch_op.drop_column('margin_used')
