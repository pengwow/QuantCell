"""add system_logs table

Revision ID: 8_add_system_logs_table
Revises: 7_add_strategy_history_table
Create Date: 2026-03-09 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8_add_system_logs_table'
down_revision: Union[str, None] = '7_add_strategy_history_table'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """升级数据库：创建system_logs表"""
    # 创建system_logs表
    op.create_table(
        'system_logs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('level', sa.String(length=20), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('module', sa.String(length=200), nullable=True),
        sa.Column('function', sa.String(length=200), nullable=True),
        sa.Column('line', sa.Integer(), nullable=True),
        sa.Column('logger_name', sa.String(length=200), nullable=True),
        sa.Column('log_type', sa.String(length=50), nullable=False),
        sa.Column('extra_data', sa.Text(), nullable=True),
        sa.Column('exception_info', sa.Text(), nullable=True),
        sa.Column('trace_id', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # 创建索引
    op.create_index('ix_system_logs_id', 'system_logs', ['id'], unique=False)
    op.create_index('ix_system_logs_timestamp', 'system_logs', ['timestamp'], unique=False)
    op.create_index('ix_system_logs_level', 'system_logs', ['level'], unique=False)
    op.create_index('ix_system_logs_log_type', 'system_logs', ['log_type'], unique=False)
    op.create_index('ix_system_logs_logger_name', 'system_logs', ['logger_name'], unique=False)
    op.create_index('ix_system_logs_trace_id', 'system_logs', ['trace_id'], unique=False)
    op.create_index('ix_system_logs_module', 'system_logs', ['module'], unique=False)
    op.create_index('ix_system_logs_created_at', 'system_logs', ['created_at'], unique=False)

    # 创建复合索引
    op.create_index('idx_system_logs_level_timestamp', 'system_logs', ['level', 'timestamp'], unique=False)
    op.create_index('idx_system_logs_type_timestamp', 'system_logs', ['log_type', 'timestamp'], unique=False)
    op.create_index('idx_system_logs_module_timestamp', 'system_logs', ['module', 'timestamp'], unique=False)


def downgrade() -> None:
    """降级数据库：删除system_logs表"""
    # 删除索引
    op.drop_index('idx_system_logs_module_timestamp', table_name='system_logs')
    op.drop_index('idx_system_logs_type_timestamp', table_name='system_logs')
    op.drop_index('idx_system_logs_level_timestamp', table_name='system_logs')
    op.drop_index('ix_system_logs_created_at', table_name='system_logs')
    op.drop_index('ix_system_logs_module', table_name='system_logs')
    op.drop_index('ix_system_logs_trace_id', table_name='system_logs')
    op.drop_index('ix_system_logs_logger_name', table_name='system_logs')
    op.drop_index('ix_system_logs_log_type', table_name='system_logs')
    op.drop_index('ix_system_logs_level', table_name='system_logs')
    op.drop_index('ix_system_logs_timestamp', table_name='system_logs')
    op.drop_index('ix_system_logs_id', table_name='system_logs')

    # 删除表
    op.drop_table('system_logs')
