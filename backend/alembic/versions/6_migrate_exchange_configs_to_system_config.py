"""Migrate exchange_configs to system_config table

Revision ID: 6
Revises: 5
Create Date: 2026-03-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
import json


# revision identifiers, used by Alembic.
revision: str = '6'
down_revision: Union[str, Sequence[str], None] = '5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Migrate exchange_configs data to system_config table."""
    conn = op.get_bind()
    
    # Check if exchange_configs table exists
    result = conn.execute(text("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='exchange_configs'
    """))
    
    if result.fetchone():
        # Migrate data from exchange_configs to system_config
        rows = conn.execute(text("""
            SELECT exchange_id, name, trading_mode, quote_currency, commission_rate,
                   api_key, api_secret, proxy_enabled, proxy_url, proxy_username,
                   proxy_password, is_default, is_enabled
            FROM exchange_configs
        """)).fetchall()
        
        for row in rows:
            exchange_id, name, trading_mode, quote_currency, commission_rate, \
            api_key, api_secret, proxy_enabled, proxy_url, proxy_username, \
            proxy_password, is_default, is_enabled = row
            
            # Build config JSON
            config_data = {
                "exchange_id": exchange_id,
                "name": name,
                "trading_mode": trading_mode or "spot",
                "quote_currency": quote_currency or "USDT",
                "commission_rate": commission_rate or 0.001,
                "api_key": api_key or "",
                "api_secret": api_secret or "",
                "proxy_enabled": bool(proxy_enabled),
                "proxy_url": proxy_url or "",
                "proxy_username": proxy_username or "",
                "proxy_password": proxy_password or "",
                "is_default": bool(is_default),
                "is_enabled": bool(is_enabled),
            }
            
            # Insert into system_config
            conn.execute(
                text("""
                    INSERT OR REPLACE INTO system_config (key, value, description, plugin, name)
                    VALUES (:key, :value, :description, :plugin, :name)
                """),
                {
                    "key": exchange_id,
                    "value": json.dumps(config_data, ensure_ascii=False),
                    "description": f"{name}交易所配置",
                    "plugin": "",
                    "name": "exchange"
                }
            )
        
        # Drop the old exchange_configs table
        op.drop_index('idx_exchange_configs_default', table_name='exchange_configs')
        op.drop_index('idx_exchange_configs_exchange_enabled', table_name='exchange_configs')
        op.drop_index(op.f('ix_exchange_configs_is_enabled'), table_name='exchange_configs')
        op.drop_index(op.f('ix_exchange_configs_is_default'), table_name='exchange_configs')
        op.drop_index(op.f('ix_exchange_configs_exchange_id'), table_name='exchange_configs')
        op.drop_index(op.f('ix_exchange_configs_id'), table_name='exchange_configs')
        op.drop_table('exchange_configs')
        
        print(f"Migrated {len(rows)} exchange configs to system_config table")


def downgrade() -> None:
    """Downgrade schema - recreate exchange_configs table."""
    # Create exchange_configs table
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
    
    # Create indexes
    op.create_index(op.f('ix_exchange_configs_id'), 'exchange_configs', ['id'], unique=False)
    op.create_index(op.f('ix_exchange_configs_exchange_id'), 'exchange_configs', ['exchange_id'], unique=False)
    op.create_index(op.f('ix_exchange_configs_is_default'), 'exchange_configs', ['is_default'], unique=False)
    op.create_index(op.f('ix_exchange_configs_is_enabled'), 'exchange_configs', ['is_enabled'], unique=False)
    op.create_index('idx_exchange_configs_exchange_enabled', 'exchange_configs', ['exchange_id', 'is_enabled'], unique=False)
    op.create_index('idx_exchange_configs_default', 'exchange_configs', ['is_default'], unique=False)
