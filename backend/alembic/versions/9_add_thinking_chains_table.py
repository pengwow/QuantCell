"""add thinking_chains table

Revision ID: 9_add_thinking_chains_table
Revises: 8_add_system_logs_table
Create Date: 2026-03-09 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9_add_thinking_chains_table'
down_revision: Union[str, None] = '8_add_system_logs_table'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """升级数据库：创建thinking_chains表"""
    # 创建thinking_chains表
    op.create_table(
        'thinking_chains',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('chain_type', sa.String(50), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('steps', sa.Text(), nullable=False),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # 创建索引
    op.create_index(op.f('ix_thinking_chains_id'), 'thinking_chains', ['id'], unique=False)
    op.create_index(op.f('ix_thinking_chains_chain_type'), 'thinking_chains', ['chain_type'], unique=False)
    op.create_index(op.f('ix_thinking_chains_is_active'), 'thinking_chains', ['is_active'], unique=False)
    op.create_index(op.f('ix_thinking_chains_created_at'), 'thinking_chains', ['created_at'], unique=False)

    # 创建联合索引
    op.create_index(
        'idx_thinking_chain_type_active',
        'thinking_chains',
        ['chain_type', 'is_active'],
        unique=False
    )
    op.create_index(
        'idx_thinking_chain_type_created',
        'thinking_chains',
        ['chain_type', 'created_at'],
        unique=False
    )


def downgrade() -> None:
    """降级数据库：删除thinking_chains表"""
    # 删除索引
    op.drop_index('idx_thinking_chain_type_created', table_name='thinking_chains')
    op.drop_index('idx_thinking_chain_type_active', table_name='thinking_chains')
    op.drop_index(op.f('ix_thinking_chains_created_at'), table_name='thinking_chains')
    op.drop_index(op.f('ix_thinking_chains_is_active'), table_name='thinking_chains')
    op.drop_index(op.f('ix_thinking_chains_chain_type'), table_name='thinking_chains')
    op.drop_index(op.f('ix_thinking_chains_id'), table_name='thinking_chains')

    # 删除表
    op.drop_table('thinking_chains')
