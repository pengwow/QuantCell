"""成交行唯一标识列改名：worker_trades.trade_id → fill_id。

命名语义一致性审计（域一 成交）：该列存的是单笔成交（fill）的标识——paper 链路为
"paper:{worker_id}:{fill_id}:{ts_ns}"、live 链路为交易所原生成交 ID——属于 fill 语境，
按词表裁决改用 fill_id；"trade" 一词保留给 round-trip 归档汇总语义（WorkerTrade 表名
不因列改名调整）。纯列改名 + 索引改名，数据零损失，downgrade 反向执行完全可逆。

不走双列灰度期的理由：这是单机自用部署，alembic upgrade 与新代码同一 commit 上线，
不存在「旧代码读新库」的窗口；双列双写只会引入同步分叉风险而不提供任何回滚收益。

Revision ID: 43
Revises: 42
Create Date: 2026-11-17
"""

import sqlalchemy as sa

from alembic import op

revision = "43"
down_revision = "42"
branch_labels = None
depends_on = None

_TABLE = "worker_trades"
_OLD, _NEW = "trade_id", "fill_id"
_OLD_IX, _NEW_IX = "idx_worker_trades_trade_id", "idx_worker_trades_fill_id"


def _column_exists(conn, table: str, column: str) -> bool:
    names = [c["name"] for c in sa.inspect(conn).get_columns(table)]
    return column in names


def _index_exists(conn, name: str) -> bool:
    return name in {ix["name"] for ix in sa.inspect(conn).get_indexes(_TABLE)}


def _swap_index(conn, old_name: str, new_name: str, column: str) -> None:
    """SQLite 无 ALTER INDEX RENAME，换名只能 drop + create（非唯一索引，无数据语义）。"""
    if _index_exists(conn, new_name) or not _index_exists(conn, old_name):
        return  # 新索引已建（重放幂等）/ 旧索引不存在（该库从未建过）则跳过
    op.drop_index(old_name, table_name=_TABLE)
    op.create_index(new_name, _TABLE, [column])


def upgrade() -> None:
    conn = op.get_bind()
    if _column_exists(conn, _TABLE, _OLD):
        op.alter_column(_TABLE, _OLD, new_column_name=_NEW)
    _swap_index(conn, _OLD_IX, _NEW_IX, _NEW)


def downgrade() -> None:
    conn = op.get_bind()
    if _column_exists(conn, _TABLE, _NEW):
        op.alter_column(_TABLE, _NEW, new_column_name=_OLD)
    _swap_index(conn, _NEW_IX, _OLD_IX, _OLD)
