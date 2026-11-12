"""跨 worker 执行锁（P0-03）：新建 order_lease。

一行 = 一个 `symbol:account_id` 锁，防止两个 worker 对同一账户同一品种
并行交易导致双向重复下单。kill -9 等无 release 的死亡由 expires_at TTL
自愈（他人条件 UPDATE 换主）。读写接口见 worker/execution_lock.py。

Revision ID: 32
Revises: 31
Create Date: 2026-11-12
"""

import sqlalchemy as sa

from alembic import op

revision = "32"
down_revision = "31"
branch_labels = None
depends_on = None


def _table_exists(table: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table)


def upgrade() -> None:
    # 幂等：create_all 建过的存量库直接跳过
    if _table_exists("order_lease"):
        return
    op.create_table(
        "order_lease",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("lease_key", sa.String(120), nullable=False),
        sa.Column("owner_worker_id", sa.Integer(), nullable=False),
        sa.Column("acquired_at", sa.DateTime(), nullable=True),
        # 心跳/过期用 time.time() 浮点秒，跨 sqlite/postgres 可比较
        sa.Column("heartbeat_at", sa.Float(), nullable=False),
        sa.Column("expires_at", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["owner_worker_id"], ["workers.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("lease_key", name="uq_order_lease_lease_key"),
    )
    op.create_index("ix_order_lease_id", "order_lease", ["id"])


def downgrade() -> None:
    if _table_exists("order_lease"):
        op.drop_table("order_lease")
