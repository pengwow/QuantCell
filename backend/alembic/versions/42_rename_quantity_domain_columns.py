"""数量域列 canonical 改名：amount→notional / filled_qty→filled_quantity / qty→quantity。

命名语义一致性审计（域三 数量）：
- worker_trades.amount → notional：该列语义是名义价值（数量×价格），与 ccxt/交易所
  响应里"下单数量"含义的 amount 解除词形重载
- worker_orders.filled_qty → filled_quantity：数量族统一 quantity 拼写，*_qty 缩写退役
- worker_fill_evidence.qty → quantity：与 WorkerTrade.quantity 同名同义
- 三者均为纯列改名，数据零损失，downgrade 反向执行完全可逆

Revision ID: 42
Revises: 41
Create Date: 2026-11-17
"""

import sqlalchemy as sa

from alembic import op

revision = "42"
down_revision = "41"
branch_labels = None
depends_on = None

# (表, 旧列, 新列)
_RENAMES = [
    ("worker_trades", "amount", "notional"),
    ("worker_orders", "filled_qty", "filled_quantity"),
    ("worker_fill_evidence", "qty", "quantity"),
]


def _column_exists(conn, table: str, column: str) -> bool:
    names = [c["name"] for c in sa.inspect(conn).get_columns(table)]
    return column in names


def upgrade() -> None:
    conn = op.get_bind()
    for table, old, new in _RENAMES:
        if not _column_exists(conn, table, old):
            continue  # 新列已存在（重放幂等）
        op.alter_column(table, old, new_column_name=new)


def downgrade() -> None:
    conn = op.get_bind()
    for table, old, new in _RENAMES:
        if not _column_exists(conn, table, new):
            continue  # 旧列已存在（重放幂等）
        op.alter_column(table, new, new_column_name=old)
