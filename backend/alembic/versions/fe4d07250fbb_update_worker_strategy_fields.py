"""update_worker_strategy_fields

Revision ID: fe4d07250fbb
Revises: 9_add_thinking_chains_table
Create Date: 2026-03-29 15:36:34.439028

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'fe4d07250fbb'
down_revision: Union[str, Sequence[str], None] = '9_add_thinking_chains_table'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 获取数据库连接
    conn = op.get_bind()
    inspector = inspect(conn)
    
    # 检查 workers 表是否存在
    if 'workers' not in inspector.get_table_names():
        # 如果表不存在，直接创建新表结构（首次创建）
        op.create_table(
            'workers',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=100), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('status', sa.String(length=20), nullable=True),
            sa.Column('strategy_id', sa.Integer(), nullable=True),
            sa.Column('strategy_name', sa.String(), nullable=True),
            sa.Column('exchange', sa.String(length=50), nullable=False),
            sa.Column('symbol', sa.String(length=50), nullable=False),
            sa.Column('timeframe', sa.String(length=10), nullable=False),
            sa.Column('market_type', sa.String(length=20), nullable=True),
            sa.Column('trading_mode', sa.String(length=10), nullable=True),
            sa.Column('cpu_limit', sa.Integer(), nullable=True),
            sa.Column('memory_limit', sa.Integer(), nullable=True),
            sa.Column('env_vars', sa.Text(), nullable=True),
            sa.Column('config', sa.Text(), nullable=True),
            sa.Column('pid', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.Column('started_at', sa.DateTime(), nullable=True),
            sa.Column('stopped_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('name', name='unique_worker_name')
        )
        op.create_index('idx_worker_status', 'workers', ['status'], unique=False)
        op.create_index('idx_worker_strategy', 'workers', ['strategy_id'], unique=False)
        op.create_index('idx_worker_strategy_name', 'workers', ['strategy_name'], unique=False)
        op.create_index('ix_workers_id', 'workers', ['id'], unique=False)
        op.create_index('ix_workers_name', 'workers', ['name'], unique=False)
        op.create_index('ix_workers_status', 'workers', ['status'], unique=False)
        return
    
    # 检查 strategy_id 列的类型
    columns = inspector.get_columns('workers')
    strategy_id_col = next((c for c in columns if c['name'] == 'strategy_id'), None)
    
    if strategy_id_col is None:
        # 如果不存在 strategy_id 列，添加它
        op.add_column('workers', sa.Column('strategy_id', sa.Integer(), nullable=True))
        op.add_column('workers', sa.Column('strategy_name', sa.String(), nullable=True))
        op.create_index('idx_worker_strategy', 'workers', ['strategy_id'], unique=False)
        op.create_index('idx_worker_strategy_name', 'workers', ['strategy_name'], unique=False)
        return
    
    # 检查 strategy_id 是否已经是 Integer 类型
    if isinstance(strategy_id_col['type'], sa.Integer):
        # 已经是 Integer，只需要添加 strategy_name 字段（如果不存在）
        if not any(c['name'] == 'strategy_name' for c in columns):
            op.add_column('workers', sa.Column('strategy_name', sa.String(), nullable=True))
            op.create_index('idx_worker_strategy_name', 'workers', ['strategy_name'], unique=False)
        return
    
    # 需要迁移：strategy_id 是 String，需要改为 Integer 并添加 strategy_name
    # SQLite 不支持直接修改列类型，需要使用表重建方式
    
    # 1. 添加临时列存储旧数据
    op.add_column('workers', sa.Column('strategy_id_temp', sa.String(), nullable=True))
    
    # 2. 将旧数据复制到临时列
    op.execute("UPDATE workers SET strategy_id_temp = strategy_id")
    
    # 3. 删除旧列
    op.drop_column('workers', 'strategy_id')
    
    # 4. 添加新列（Integer 类型）
    op.add_column('workers', sa.Column('strategy_id', sa.Integer(), nullable=True))
    
    # 5. 添加 strategy_name 列
    op.add_column('workers', sa.Column('strategy_name', sa.String(), nullable=True))
    
    # 6. 将临时列数据复制到 strategy_name
    op.execute("UPDATE workers SET strategy_name = strategy_id_temp WHERE strategy_id_temp IS NOT NULL")
    
    # 7. 删除临时列
    op.drop_column('workers', 'strategy_id_temp')
    
    # 8. 重新创建索引
    op.drop_index('idx_worker_strategy', table_name='workers')
    op.create_index('idx_worker_strategy', 'workers', ['strategy_id'], unique=False)
    op.create_index('idx_worker_strategy_name', 'workers', ['strategy_name'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()
    inspector = inspect(conn)
    
    if 'workers' not in inspector.get_table_names():
        return
    
    columns = inspector.get_columns('workers')
    
    # 检查是否需要降级
    strategy_id_col = next((c for c in columns if c['name'] == 'strategy_id'), None)
    if strategy_id_col is None:
        return
    
    # 如果 strategy_id 已经是 String，无需降级
    if isinstance(strategy_id_col['type'], sa.String):
        return
    
    # 需要降级回 String 类型
    # 1. 添加临时列存储 strategy_name 数据
    op.add_column('workers', sa.Column('strategy_name_temp', sa.String(), nullable=True))
    
    # 2. 将 strategy_name 数据复制到临时列
    op.execute("UPDATE workers SET strategy_name_temp = strategy_name WHERE strategy_name IS NOT NULL")
    
    # 3. 删除新的 strategy_id (Integer) 和 strategy_name 字段
    op.drop_column('workers', 'strategy_id')
    op.drop_column('workers', 'strategy_name')
    
    # 4. 添加旧的 strategy_id 字段 (String)
    op.add_column('workers', sa.Column('strategy_id', sa.String(), nullable=True))
    
    # 5. 将临时字段数据复制回 strategy_id
    op.execute("UPDATE workers SET strategy_id = strategy_name_temp WHERE strategy_name_temp IS NOT NULL")
    
    # 6. 删除临时字段
    op.drop_column('workers', 'strategy_name_temp')
    
    # 7. 重新创建索引
    op.create_index('idx_worker_strategy', 'workers', ['strategy_id'], unique=False)
