"""成交证据链（P0-01）：worker_trades 加订单意图两列 + 新建 worker_fill_evidence。

worker_fill_evidence 以 venue_trade_id（交易所原生成交 ID）为幂等主锚（唯一约束），
client_order_id 关联 worker_orders.client_order_id（OMS UUID），live 同步器将
worker_trades 与本表同事务双写，恢复同步 / 对账都以本表为「这笔成交已经应用过」
的证据，防跨路径重复入账。

Revision ID: 30
Revises: 29
Create Date: 2026-11-11
"""

import sqlalchemy as sa

from alembic import op

revision = "30"
down_revision = "29"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    try:
        return {col["name"] for col in inspector.get_columns(table)}
    except sa.exc.NoSuchTableError:
        return set()


def _indexes(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    try:
        return {idx["name"] for idx in inspector.get_indexes(table)}
    except sa.exc.NoSuchTableError:
        return set()


def _table_exists(table: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table)


def upgrade() -> None:
    # 幂等：create_all 建过的存量库直接跳过
    if "client_order_id" not in _columns("worker_trades"):
        op.add_column("worker_trades", sa.Column("client_order_id", sa.String(100), nullable=True))
    if "venue_order_id" not in _columns("worker_trades"):
        op.add_column("worker_trades", sa.Column("venue_order_id", sa.String(100), nullable=True))
    if "idx_worker_trades_client_order_id" not in _indexes("worker_trades"):
        op.create_index("idx_worker_trades_client_order_id", "worker_trades", ["client_order_id"])

    if not _table_exists("worker_fill_evidence"):
        op.create_table(
            "worker_fill_evidence",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("worker_id", sa.Integer(), nullable=False),
            sa.Column("client_order_id", sa.String(100), nullable=False),
            sa.Column("venue_order_id", sa.String(100), nullable=True),
            sa.Column("venue_trade_id", sa.String(64), nullable=False),
            sa.Column("symbol", sa.String(50), nullable=False),
            sa.Column("side", sa.String(10), nullable=False),
            sa.Column("qty", sa.Float(), nullable=False),
            sa.Column("price", sa.Float(), nullable=True),
            sa.Column("fee", sa.Float(), nullable=True),
            sa.Column("applied_at", sa.DateTime(), nullable=True),
            sa.Column("source", sa.String(20), nullable=False),
            sa.ForeignKeyConstraint(["worker_id"], ["workers.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_worker_fill_evidence_id", "worker_fill_evidence", ["id"])
        op.create_index("ix_worker_fill_evidence_worker_id", "worker_fill_evidence", ["worker_id"])
        op.create_index("ix_worker_fill_evidence_client_order_id", "worker_fill_evidence", ["client_order_id"])
        op.create_index(
            "uq_worker_fill_evidence_venue_trade_id", "worker_fill_evidence", ["venue_trade_id"], unique=True
        )


def downgrade() -> None:
    if _table_exists("worker_fill_evidence"):
        op.drop_table("worker_fill_evidence")
    if "idx_worker_trades_client_order_id" in _indexes("worker_trades"):
        op.drop_index("idx_worker_trades_client_order_id", table_name="worker_trades")
    cols = _columns("worker_trades")
    for col in ("venue_order_id", "client_order_id"):
        if col in cols:
            op.drop_column("worker_trades", col)
