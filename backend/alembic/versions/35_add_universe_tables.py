"""标的池（P2-03）：universes / universe_memberships / universe_snapshots 三表。

universe = 可命名的一篮子交易对集合；membership 以 included_from/until 表达成分
历史（included_until 为 NULL 即当前成员）；snapshot 在建池与每次成分变更时写入
完整成分 JSON，供按时间回看。同名序号空缺不存在，本迁移 down 指向 34。

Revision ID: 35
Revises: 34
Create Date: 2026-11-12
"""

import sqlalchemy as sa

from alembic import op

revision = "35"
down_revision = "34"
branch_labels = None
depends_on = None


def _existing_tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    # 幂等：create_all 双通道建过的存量库直接跳过
    tables = _existing_tables()
    if "universes" not in tables:
        op.create_table(
            "universes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(100), nullable=False, unique=True),
            sa.Column("description", sa.String(500), nullable=True),
            sa.Column("owner_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
    if "universe_memberships" not in tables:
        op.create_table(
            "universe_memberships",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("universe_id", sa.Integer(), nullable=False),
            sa.Column("symbol", sa.String(50), nullable=False),
            sa.Column("included_from", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("included_until", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_universe_memberships_universe_id", "universe_memberships", ["universe_id"])
        op.create_index("ix_universe_memberships_universe_symbol", "universe_memberships", ["universe_id", "symbol"])
    if "universe_snapshots" not in tables:
        op.create_table(
            "universe_snapshots",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("universe_id", sa.Integer(), nullable=False),
            sa.Column("symbols", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_universe_snapshots_universe_id", "universe_snapshots", ["universe_id"])


def downgrade() -> None:
    tables = _existing_tables()
    if "universe_snapshots" in tables:
        op.drop_index("ix_universe_snapshots_universe_id", table_name="universe_snapshots")
        op.drop_table("universe_snapshots")
    if "universe_memberships" in tables:
        op.drop_index("ix_universe_memberships_universe_symbol", table_name="universe_memberships")
        op.drop_index("ix_universe_memberships_universe_id", table_name="universe_memberships")
        op.drop_table("universe_memberships")
    if "universes" in tables:
        op.drop_table("universes")
