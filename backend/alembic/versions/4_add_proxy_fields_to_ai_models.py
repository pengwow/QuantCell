"""Add proxy fields to ai_models table

Revision ID: 4
Revises: 3
Create Date: 2026-03-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4'
down_revision: Union[str, Sequence[str], None] = '3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 添加代理字段到ai_models表
    op.add_column('ai_models', sa.Column('proxy_enabled', sa.Boolean(), default=False, nullable=True))
    op.add_column('ai_models', sa.Column('proxy_url', sa.String(), nullable=True))
    op.add_column('ai_models', sa.Column('proxy_username', sa.String(), nullable=True))
    op.add_column('ai_models', sa.Column('proxy_password', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    # 删除代理字段
    op.drop_column('ai_models', 'proxy_password')
    op.drop_column('ai_models', 'proxy_username')
    op.drop_column('ai_models', 'proxy_url')
    op.drop_column('ai_models', 'proxy_enabled')
