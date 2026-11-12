"""同步游标持久化（P0-02）：新建 worker_sync_cursor。

live 成交同步器按 (worker_id, account_id) 记录上次提交位置（毫秒时间戳 +
同毫秒兜底 trade id），进程重启后从游标续拉，替代「每次启动固定只拉最近
6 小时」的保守窗口（该窗口超过 6h 的停机会漏单）。

Revision ID: 31
Revises: 30
Create Date: 2026-11-11
"""

import sqlalchemy as sa

from alembic import op

revision = "31"
down_revision = "30"
branch_labels = None
depends_on = None


def _table_exists(table: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table)


def upgrade() -> None:
    # 幂等：create_all 建过的存量库直接跳过
    if _table_exists("worker_sync_cursor"):
        return
    op.create_table(
        "worker_sync_cursor",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("worker_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.String(100), nullable=False, server_default=""),
        sa.Column("cursor_ts", sa.BigInteger(), nullable=False),
        sa.Column("cursor_trade_id", sa.String(64), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["worker_id"], ["workers.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("worker_id", "account_id"),
    )
    op.create_index("ix_worker_sync_cursor_id", "worker_sync_cursor", ["id"])
    op.create_index("ix_worker_sync_cursor_worker_id", "worker_sync_cursor", ["worker_id"])


def downgrade() -> None:
    if _table_exists("worker_sync_cursor"):
        op.drop_table("worker_sync_cursor")
