"""Initial migration

Revision ID: 1a960941d752
Revises: 
Create Date: 2026-01-26 18:45:56.243596

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '1a960941d752'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - NOOP.

    All tables and indexes were already created via Base.metadata.create_all()
    before Alembic was activated. This migration only serves as a version stamp
    so that subsequent migrations can build on top of the existing schema.
    The original auto-generated operations (alter_column with sa.Identity,
    create_index for system_config) are all redundant because the objects
    already exist in the SQLite database.
    """
    pass


def downgrade() -> None:
    """Downgrade schema - NOOP (symmetric with upgrade)."""
    pass
