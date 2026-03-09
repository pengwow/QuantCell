"""add strategy_history table

Revision ID: 7_add_strategy_history_table
Revises: ed0da7529e75
Create Date: 2026-03-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7_add_strategy_history_table'
down_revision: Union[str, Sequence[str], None] = 'ed0da7529e75'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 创建 strategy_history 表
    op.create_table(
        'strategy_history',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('user_id', sa.String(255), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('requirement', sa.Text(), nullable=False),
        sa.Column('code', sa.Text(), nullable=False),
        sa.Column('explanation', sa.Text(), nullable=True),
        sa.Column('model_id', sa.String(255), nullable=True),
        sa.Column('temperature', sa.Float(), nullable=True),
        sa.Column('tokens_used', sa.Text(), nullable=True),
        sa.Column('generation_time', sa.Float(), nullable=True),
        sa.Column('is_valid', sa.Boolean(), default=True),
        sa.Column('tags', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # 创建索引
    op.create_index(op.f('ix_strategy_history_id'), 'strategy_history', ['id'], unique=False)
    op.create_index(op.f('ix_strategy_history_user_id'), 'strategy_history', ['user_id'], unique=False)
    op.create_index(op.f('ix_strategy_history_is_valid'), 'strategy_history', ['is_valid'], unique=False)
    op.create_index(op.f('ix_strategy_history_created_at'), 'strategy_history', ['created_at'], unique=False)

    # 创建联合索引
    op.create_index(
        'idx_strategy_history_user_created',
        'strategy_history',
        ['user_id', 'created_at'],
        unique=False
    )
    op.create_index(
        'idx_strategy_history_user_valid',
        'strategy_history',
        ['user_id', 'is_valid'],
        unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    # 删除索引
    op.drop_index('idx_strategy_history_user_valid', table_name='strategy_history')
    op.drop_index('idx_strategy_history_user_created', table_name='strategy_history')
    op.drop_index(op.f('ix_strategy_history_created_at'), table_name='strategy_history')
    op.drop_index(op.f('ix_strategy_history_is_valid'), table_name='strategy_history')
    op.drop_index(op.f('ix_strategy_history_user_id'), table_name='strategy_history')
    op.drop_index(op.f('ix_strategy_history_id'), table_name='strategy_history')

    # 删除表
    op.drop_table('strategy_history')
