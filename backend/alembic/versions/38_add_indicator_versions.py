"""指标版本快照（P2-08）。

indicator_versions 存储指标每次保存/回滚产生的代码快照（version_no 递增），
indicators 表新增 version 列记录当前版本号；版本列表/回滚/diff 见
backend/indicators/versions.py。本迁移 down 指向 37。

Revision ID: 38
Revises: 37
Create Date: 2026-11-12
"""

import sqlalchemy as sa

from alembic import op

revision = "38"
down_revision = "37"
branch_labels = None
depends_on = None


def _existing_tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _existing_columns(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    # 幂等：indicators 加 version 列（存量库 create_all 双通道建表时列已存在则跳过）
    if "indicators" in _existing_tables() and "version" not in _existing_columns("indicators"):
        op.add_column("indicators", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))

    if "indicator_versions" in _existing_tables():
        return
    op.create_table(
        "indicator_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("indicator_id", sa.Integer(), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("source", sa.String(20), nullable=False, server_default="save"),  # create/save/rollback
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("indicator_id", "version_no", name="uq_indicator_versions_id_no"),
    )
    op.create_index("ix_indicator_versions_id", "indicator_versions", ["id"])
    op.create_index("ix_indicator_versions_indicator_id", "indicator_versions", ["indicator_id"])


def downgrade() -> None:
    tables = _existing_tables()
    if "indicator_versions" in tables:
        op.drop_index("ix_indicator_versions_indicator_id", table_name="indicator_versions")
        op.drop_index("ix_indicator_versions_id", table_name="indicator_versions")
        op.drop_table("indicator_versions")
    if "indicators" in tables and "version" in _existing_columns("indicators"):
        # SQLite 删列需要 batch 模式重建表
        with op.batch_alter_table("indicators") as batch:
            batch.drop_column("version")
