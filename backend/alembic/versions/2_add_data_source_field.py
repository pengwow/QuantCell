"""Add data_source field to kline tables

Revision ID: 2
Revises: 1a960941d752
Create Date: 2026-01-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2'
down_revision: Union[str, Sequence[str], None] = '1a960941d752'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add data_source field to crypto_future_klines table
    op.add_column('crypto_future_klines', sa.Column('data_source', sa.String(length=50), nullable=False, server_default='unknown'))
    op.create_index(op.f('ix_crypto_future_klines_data_source'), 'crypto_future_klines', ['data_source'], unique=False)
    
    # Add data_source field to stock_klines table
    op.add_column('stock_klines', sa.Column('data_source', sa.String(length=50), nullable=False, server_default='unknown'))
    op.create_index(op.f('ix_stock_klines_data_source'), 'stock_klines', ['data_source'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    # Remove data_source field from stock_klines table
    op.drop_index(op.f('ix_stock_klines_data_source'), table_name='stock_klines')
    op.drop_column('stock_klines', 'data_source')
    
    # Remove data_source field from crypto_future_klines table
    op.drop_index(op.f('ix_crypto_future_klines_data_source'), table_name='crypto_future_klines')
    op.drop_column('crypto_future_klines', 'data_source')
