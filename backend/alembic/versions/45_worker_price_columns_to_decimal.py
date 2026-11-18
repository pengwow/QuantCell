"""worker 域 6 个价格列 Float→DECIMAL(30, 8)（命名语义审计 P2-7）。

数值语义收口：价格列入交易台账，历史 Float 存储的二进制尾数误差（0.1+0.2 之类）
不适合对账；对齐 K线 volume / ticker 先例迁移 DECIMAL(30, 8)。读取端没有逐点
float() 收口，worker/models.py 的 PriceAsFloat(TypeDecorator) 在模型层统一
"DECIMAL 存储、float 读出"（DuckDB 等 native decimal 方言 asdecimal=False 不生效，
必须在装饰器层转换），本迁移只负责物理类型。

与 K线 volume 迁移（collector 自迁移 DROP+重建）的关键差异：worker 四表是交易
台账、数据不可重拉，必须原地改型保数据——SQLite 用 batch_alter_table 整表重建
（迁移时拷贝数据），PG 直接 ALTER COLUMN。新库由 create_all 按 PriceAsFloat
建 DECIMAL，inspector 发现已是 Numeric 时幂等跳过。

天花板（ponytail:）：SQLite batch 重建在迁移事务外做逐表拷贝，大表会锁写较久；
worker_trades 千行级远未到，不引入 online DDL。
"""

import sqlalchemy as sa
from sqlalchemy import Numeric
from sqlalchemy import inspect as sa_inspect

from alembic import op

revision = "45"
down_revision = "44"
branch_labels = None
depends_on = None

# (表, 列)：覆盖测试门禁基线中全部 6 个价格列（P2-6 添加的 float 台账）
_PRICE_COLUMNS = [
    ("worker_trades", "price"),
    ("worker_orders", "price"),
    ("worker_orders", "avg_fill_price"),
    ("worker_positions", "entry_price"),
    ("worker_positions", "current_price"),
    ("worker_fill_evidence", "price"),
]

_DECIMAL = sa.Numeric(30, 8)
_FLOAT = sa.Float()


def _pending_columns(conn) -> list[tuple[str, str]]:
    """过滤出仍是 Float 的价格列（新库 create_all 已按 DECIMAL 建好时为空，幂等）。

    注意不能只判 isinstance(t, Numeric)：sa.Float 是 sa.Numeric 的子类，Float 列
    会误判为已迁移（曾在真实库上静默跳过整次迁移），须排除 Float。
    """
    inspector = sa_inspect(conn)
    cache: dict[str, dict[str, object]] = {}
    pending = []
    for table, column in _PRICE_COLUMNS:
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
    for table, column in _PRICE_COLUMNS:
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
