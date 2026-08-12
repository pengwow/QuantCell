"""remove_share_views_table

彻底下线本地分享模式，删除 share_views 表：
- 公开只读页不再提供
- 访问审计/限速统计完全由远端 quantcell.top 端负责
- view_count 字段保留在 share_tokens 表中作为兼容字段，不再自增

Revision ID: 18
Revises: 17
Create Date: 2026-06-08 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '18'
down_revision: Union[str, Sequence[str], None] = '17'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """下线本地分享：删除 share_views 表（公开访问审计不再需要）"""
    op.drop_index('idx_share_views_ip_time', table_name='share_views')
    op.drop_index('idx_share_views_token', table_name='share_views')
    op.drop_table('share_views')


def downgrade() -> None:
    """回滚：重建 share_views 表（用于历史数据回退）"""
    op.create_table(
        'share_views',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('token_id', sa.Integer(), nullable=False),
        sa.Column('ip', sa.String(length=64), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('viewed_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('success', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.ForeignKeyConstraint(['token_id'], ['share_tokens.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_share_views_token', 'share_views', ['token_id'], unique=False)
    op.create_index('idx_share_views_ip_time', 'share_views', ['ip', 'viewed_at'], unique=False)
