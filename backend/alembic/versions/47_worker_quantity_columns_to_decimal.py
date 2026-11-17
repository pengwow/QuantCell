"""worker 域 17 个数量/资金账务列 Float→DECIMAL(30, 8)（命名语义审计 P2-12）。

数量与资金列入交易台账（quantity/fee/pnl/capital 族），与价格列（P2-7）同受
float 台账二进制尾数误差之害；对齐迁移 45 的先例收口 DECIMAL(30, 8)。模型层
读写由 worker/models.py 的 PriceAsFloat(TypeDecorator) 统一（该装饰器语义是
通用的「账务列 DECIMAL 存储 float 读出」，P2-12 起数量/资金族复用，见类
docstring），本迁移只负责物理类型。

聚合统计与风控配置列为数量域 B 层豁免（total_profit/stop_loss_pct/leverage
等展示比率与阈值参数，Float 危害可忽略），保持 Float，不在本迁移名单。

结构照抄迁移 45：SQLite batch 整表重建保数据，PG 显式 cast，inspector 幂等
跳过（Float 是 Numeric 子类，须显式排除，勿删该分支）。

天花板（ponytail:）：同迁移 45，batch 重建逐表拷贝锁写，台账量级未到 online DDL。
"""

import sqlalchemy as sa
from sqlalchemy import Numeric
from sqlalchemy import inspect as sa_inspect

from alembic import op

revision = "47"
down_revision = "46"
branch_labels = None
depends_on = None

# (表, 列)：账务逐笔/逐仓/资金列全覆盖；realized_pnl_pct（trades）与统计、
# 风控配置族的 pct/ratio 列属 B 层豁免，故意不在名单
_MONEY_COLUMNS = [
    ("worker_trades", "quantity"),
    ("worker_trades", "notional"),
    ("worker_trades", "fee"),
    ("worker_trades", "realized_pnl"),
    ("worker_orders", "quantity"),
    ("worker_orders", "filled_quantity"),
    ("worker_positions", "quantity"),
    ("worker_positions", "unrealized_pnl"),
    ("worker_positions", "realized_pnl"),
    ("worker_positions", "margin_used"),
    ("worker_fill_evidence", "quantity"),
    ("worker_fill_evidence", "fee"),
    ("worker_capital", "initial_capital"),
    ("worker_capital", "current_capital"),
    ("worker_capital", "available_capital"),
    ("worker_capital", "frozen_capital"),
    ("worker_capital", "margin_used"),
]

_DECIMAL = sa.Numeric(30, 8)
_FLOAT = sa.Float()


def _pending_columns(conn) -> list[tuple[str, str]]:
    """过滤出仍是 Float 的账务列（新库 create_all 已按 DECIMAL 建好时为空，幂等）。"""
    inspector = sa_inspect(conn)
    cache: dict[str, dict[str, object]] = {}
    pending = []
    for table, column in _MONEY_COLUMNS:
        if table not in cache:
            cache[table] = {c["name"]: c["type"] for c in inspector.get_columns(table)}
        col_type = cache[table][column]
        if isinstance(col_type, sa.Float) or not isinstance(col_type, Numeric):
            pending.append((table, column))
    return pending


def upgrade() -> None:
    conn = op.get_bind()
    pending = _pending_columns(conn)
    if not pending:
        return
    for table, column in pending:
        if conn.dialect.name == "sqlite":
            # SQLite 无 ALTER COLUMN TYPE，batch 模式自动反射整表并拷贝数据
            with op.batch_alter_table(table) as batch_op:
                batch_op.alter_column(column, existing_type=_FLOAT, type_=_DECIMAL)
        else:
            # 显式 cast 保数据；PG 端 DECIMAL 即强类型
            op.alter_column(
                table,
                column,
                existing_type=_FLOAT,
                type_=_DECIMAL,
                postgresql_using=f"{column}::numeric(30, 8)",
            )


def downgrade() -> None:
    conn = op.get_bind()
    for table, column in _MONEY_COLUMNS:
        if conn.dialect.name == "sqlite":
            with op.batch_alter_table(table) as batch_op:
                batch_op.alter_column(column, existing_type=_DECIMAL, type_=_FLOAT)
        else:
            op.alter_column(
                table,
                column,
                existing_type=_DECIMAL,
                type_=_FLOAT,
                postgresql_using=f"{column}::double precision",
            )
