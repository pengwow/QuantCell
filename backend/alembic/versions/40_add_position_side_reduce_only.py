"""方向词汇统一：订单/成交表加声明字段，持仓表列改名，存量大小写归一。

设计文档：docs/superpowers/specs/2026-11-16-direction-vocab-unification-design.md §4.2
- worker_orders / worker_trades 各加 position_side（声明值，存量回填 'both'）与
  reduce_only（恒 0）；worker_positions.side → position_side（SQLite ≥3.25 原生
  RENAME COLUMN）；三表存量大写一律 UPDATE 小写化——写入侧归一在 vocab 层，本迁移
  负责存量。幂等：每个 DDL 前查 inspector，create_all 双通道先建好的目标 schema 直接跳过。

Revision ID: 40
Revises: 39
Create Date: 2026-11-16
"""

import sqlalchemy as sa

from alembic import op

revision = "40"
down_revision = "39"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _add_vocab_columns(table: str) -> None:
    """订单/成交两表共用的加列逻辑（列型与 models.py 对齐）。"""
    cols = _columns(table)
    if "position_side" not in cols:
        op.add_column(
            table,
            sa.Column("position_side", sa.String(10), nullable=False, server_default="both"),
        )
    if "reduce_only" not in cols:
        op.add_column(table, sa.Column("reduce_only", sa.Boolean(), nullable=False, server_default="0"))


def upgrade() -> None:
    tables = _tables()

    if "worker_orders" in tables:
        _add_vocab_columns("worker_orders")
        # 存量大写归一（canonical 小写，铁律1）；LOWER 对 ASCII 枚举值足够
        op.execute("UPDATE worker_orders SET side = LOWER(side)")

    if "worker_trades" in tables:
        _add_vocab_columns("worker_trades")

    if "worker_positions" in tables:
        cols = _columns("worker_positions")
        if "side" in cols and "position_side" not in cols:
            # alembic 无 rename_column API，标准改名走 alter_column(new_column_name=)
            op.alter_column("worker_positions", "side", new_column_name="position_side")
            op.execute("UPDATE worker_positions SET position_side = LOWER(position_side)")


def downgrade() -> None:
    tables = _tables()

    if "worker_positions" in tables:
        cols = _columns("worker_positions")
        if "position_side" in cols:
            op.alter_column("worker_positions", "position_side", new_column_name="side")

    for table in ("worker_orders", "worker_trades"):
        if table in tables:
            cols = _columns(table)
            for col in ("reduce_only", "position_side"):
                if col in cols:
                    op.drop_column(table, col)
