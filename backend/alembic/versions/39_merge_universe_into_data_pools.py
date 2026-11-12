"""标的池并入自选组：建 data_pool_snapshots，清理废弃的 universe 三表。

universe 模块（P2-03）与自选组（data_pools）概念重复，已整体并入 data_pools 体系：
- 自选组成分增删后写入 data_pool_snapshots（变更后的完整成分 JSON）；
- 回测/因子改用 pool_id 按 DataPoolBusiness.resolve_symbols 取成分；
- universes / universe_memberships / universe_snapshots 三表废弃并在此清理。
  注意：drop 不可逆，downgrade 只按 35 的结构重建空表，不恢复数据。

Revision ID: 39
Revises: 38
Create Date: 2026-11-12
"""

import sqlalchemy as sa

from alembic import op

revision = "39"
down_revision = "38"
branch_labels = None
depends_on = None


def _existing_tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    # 幂等建 data_pool_snapshots（存量库 create_all 双通道可能已建）
    if "data_pool_snapshots" not in _existing_tables():
        op.create_table(
            "data_pool_snapshots",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("pool_id", sa.Integer(), nullable=False),
            sa.Column("symbols", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_data_pool_snapshots_id", "data_pool_snapshots", ["id"])
        op.create_index("ix_data_pool_snapshots_pool_id", "data_pool_snapshots", ["pool_id"])

    # 清理废弃的 universe 三表（模块已删除，留着只会误导）
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


def downgrade() -> None:
    # 按 35 的原始结构重建三表（数据不恢复，见文件头注释）
    if "universes" not in _existing_tables():
        op.create_table(
            "universes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(100), nullable=False, unique=True),
            sa.Column("description", sa.String(500), nullable=True),
            sa.Column("owner_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
    if "universe_memberships" not in _existing_tables():
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
    if "universe_snapshots" not in _existing_tables():
        op.create_table(
            "universe_snapshots",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("universe_id", sa.Integer(), nullable=False),
            sa.Column("symbols", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_universe_snapshots_universe_id", "universe_snapshots", ["universe_id"])

    tables = _existing_tables()
    if "data_pool_snapshots" in tables:
        op.drop_index("ix_data_pool_snapshots_pool_id", table_name="data_pool_snapshots")
        op.drop_index("ix_data_pool_snapshots_id", table_name="data_pool_snapshots")
        op.drop_table("data_pool_snapshots")
