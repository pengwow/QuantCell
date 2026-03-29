"""remove_old_worker_trading_columns

Revision ID: 11
Revises: 10
Create Date: 2026-03-29 22:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = '11'
down_revision: Union[str, Sequence[str], None] = '10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - 删除 workers 表的旧交易配置列."""
    conn = op.get_bind()
    inspector = inspect(conn)

    # 检查 workers 表是否存在
    if 'workers' not in inspector.get_table_names():
        return

    columns = {c['name']: c for c in inspector.get_columns('workers')}

    # 删除旧的交易配置列（如果存在）
    # 这些列现在已经被 trading_config JSON 字段替代
    if 'exchange' in columns:
        op.drop_column('workers', 'exchange')
    if 'symbol' in columns:
        op.drop_column('workers', 'symbol')
    if 'timeframe' in columns:
        op.drop_column('workers', 'timeframe')
    if 'market_type' in columns:
        op.drop_column('workers', 'market_type')
    if 'trading_mode' in columns:
        op.drop_column('workers', 'trading_mode')


def downgrade() -> None:
    """Downgrade schema - 恢复旧的交易配置列."""
    conn = op.get_bind()
    inspector = inspect(conn)

    if 'workers' not in inspector.get_table_names():
        return

    columns = {c['name']: c for c in inspector.get_columns('workers')}

    # 恢复旧列（如果 trading_config 存在）
    if 'trading_config' in columns:
        if 'exchange' not in columns:
            op.add_column('workers', sa.Column('exchange', sa.String(length=50), nullable=True))
        if 'symbol' not in columns:
            op.add_column('workers', sa.Column('symbol', sa.String(length=50), nullable=True))
        if 'timeframe' not in columns:
            op.add_column('workers', sa.Column('timeframe', sa.String(length=10), nullable=True))
        if 'market_type' not in columns:
            op.add_column('workers', sa.Column('market_type', sa.String(length=20), nullable=True))
        if 'trading_mode' not in columns:
            op.add_column('workers', sa.Column('trading_mode', sa.String(length=10), nullable=True))
