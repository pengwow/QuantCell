"""Add ai_models table for AI model configuration

Revision ID: 3
Revises: 2
Create Date: 2026-03-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3'
down_revision: Union[str, Sequence[str], None] = '2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 创建ai_models表
    op.create_table(
        'ai_models',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('provider', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('api_key', sa.Text(), nullable=False),
        sa.Column('api_host', sa.String(), nullable=True),
        sa.Column('models', sa.Text(), nullable=True),
        sa.Column('is_default', sa.Boolean(), default=False),
        sa.Column('is_enabled', sa.Boolean(), default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # 创建索引
    op.create_index(op.f('ix_ai_models_id'), 'ai_models', ['id'], unique=False)
    op.create_index(op.f('ix_ai_models_provider'), 'ai_models', ['provider'], unique=False)
    op.create_index(op.f('ix_ai_models_is_default'), 'ai_models', ['is_default'], unique=False)
    op.create_index(op.f('ix_ai_models_is_enabled'), 'ai_models', ['is_enabled'], unique=False)
    op.create_index('idx_ai_models_provider_enabled', 'ai_models', ['provider', 'is_enabled'], unique=False)
    op.create_index('idx_ai_models_default', 'ai_models', ['is_default'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    # 删除索引
    op.drop_index('idx_ai_models_default', table_name='ai_models')
    op.drop_index('idx_ai_models_provider_enabled', table_name='ai_models')
    op.drop_index(op.f('ix_ai_models_is_enabled'), table_name='ai_models')
    op.drop_index(op.f('ix_ai_models_is_default'), table_name='ai_models')
    op.drop_index(op.f('ix_ai_models_provider'), table_name='ai_models')
    op.drop_index(op.f('ix_ai_models_id'), table_name='ai_models')
    
    # 删除表
    op.drop_table('ai_models')
