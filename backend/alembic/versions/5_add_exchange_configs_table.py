"""Add exchange_configs table for exchange configuration

Revision ID: 5
Revises: 4
Create Date: 2026-03-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5'
down_revision: Union[str, Sequence[str], None] = '4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 创建exchange_configs表
    op.create_table(
        'exchange_configs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('exchange_id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('trading_mode', sa.String(), default='spot'),
        sa.Column('quote_currency', sa.String(), default='USDT'),
        sa.Column('commission_rate', sa.Float(), default=0.001),
        sa.Column('api_key', sa.Text(), nullable=True),
        sa.Column('api_secret', sa.Text(), nullable=True),
        sa.Column('proxy_enabled', sa.Boolean(), default=False),
        sa.Column('proxy_url', sa.String(), nullable=True),
        sa.Column('proxy_username', sa.String(), nullable=True),
        sa.Column('proxy_password', sa.String(), nullable=True),
        sa.Column('is_default', sa.Boolean(), default=False),
        sa.Column('is_enabled', sa.Boolean(), default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # 创建索引
    op.create_index(op.f('ix_exchange_configs_id'), 'exchange_configs', ['id'], unique=False)
    op.create_index(op.f('ix_exchange_configs_exchange_id'), 'exchange_configs', ['exchange_id'], unique=False)
    op.create_index(op.f('ix_exchange_configs_is_default'), 'exchange_configs', ['is_default'], unique=False)
    op.create_index(op.f('ix_exchange_configs_is_enabled'), 'exchange_configs', ['is_enabled'], unique=False)
    op.create_index('idx_exchange_configs_exchange_enabled', 'exchange_configs', ['exchange_id', 'is_enabled'], unique=False)
    op.create_index('idx_exchange_configs_default', 'exchange_configs', ['is_default'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    # 删除索引
    op.drop_index('idx_exchange_configs_default', table_name='exchange_configs')
    op.drop_index('idx_exchange_configs_exchange_enabled', table_name='exchange_configs')
    op.drop_index(op.f('ix_exchange_configs_is_enabled'), table_name='exchange_configs')
    op.drop_index(op.f('ix_exchange_configs_is_default'), table_name='exchange_configs')
    op.drop_index(op.f('ix_exchange_configs_exchange_id'), table_name='exchange_configs')
    op.drop_index(op.f('ix_exchange_configs_id'), table_name='exchange_configs')
    
    # 删除表
    op.drop_table('exchange_configs')
