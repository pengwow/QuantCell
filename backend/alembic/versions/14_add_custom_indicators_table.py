"""add_custom_indicators_table

Revision ID: 14
Revises: 12
Create Date: 2026-04-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '14'
down_revision: Union[str, Sequence[str], None] = '12'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('indicators',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), server_default='', nullable=True),
        sa.Column('code', sa.Text(), nullable=False),
        sa.Column('is_encrypted', sa.Boolean(), server_default='0', nullable=True),
        sa.Column('publish_to_community', sa.Boolean(), server_default='0', nullable=True),
        sa.Column('pricing_type', sa.String(20), server_default='free', nullable=True),
        sa.Column('price', sa.Numeric(10, 2), server_default='0', nullable=True),
        sa.Column('preview_image', sa.String(500), server_default='', nullable=True),
        sa.Column('review_status', sa.String(20), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_indicators_id'), 'indicators', ['id'], unique=False)
    op.create_index(op.f('ix_indicators_user_id'), 'indicators', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_indicators_user_id'), table_name='indicators')
    op.drop_index(op.f('ix_indicators_id'), table_name='indicators')
    op.drop_table('indicators')
