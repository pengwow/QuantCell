"""收件箱逐行已读语义升级 + async_task_records 任务影子表。

1) notifications 加 read_at / processed_at：
   未读判定从「id > notification_state.last_read_id 水位比较」升级为
   「read_at IS NULL」逐行标记。动机：任务终态通知需要单条已读、
   以及任务类通知已读即归档（processed_at）的逐行语义，水位表无法表达。
   notification_state 停用不删（模型与历史单行保留，代码不再读写），
   旧链路（< 48）回滚后仍可用；inbox.py 本次同步移除全部水位引用。
   存量按旧水位语义等价回填：id <= last_read_id → read_at = created_at，
   无水位行视为全部未读（不回填）。

2) 新表 async_task_records：rl_train / factor_job 两域的终态影子表，
   服务重启后补偿扫描（compensate_interrupted_tasks）依据。

幂等：按迁移 45/47 先例，inspector 检测列/表已存在则跳过
（新库 create_all 按新 schema 建立，迁移空跑）。
天花板（ponytail:）：SQLite batch 重建整表锁写；notifications 为单管理员
自部署流水表，量级远未到 online DDL 的必要。
"""

import sqlalchemy as sa
from sqlalchemy import inspect as sa_inspect

from alembic import op

revision = "48"
down_revision = "47"
branch_labels = None
depends_on = None


def _has_table(conn, table: str) -> bool:
    return sa_inspect(conn).has_table(table)


def _add_column_if_missing(conn, table: str, column: sa.Column) -> None:
    names = {c["name"] for c in sa_inspect(conn).get_columns(table)}
    if column.name in names:
        return
    if conn.dialect.name == "sqlite":
        # SQLite 无 ADD COLUMN 事务保证差异，走 batch 兼容路径
        with op.batch_alter_table(table) as batch_op:
            batch_op.add_column(column)
    else:
        op.add_column(table, column)


def upgrade() -> None:
    conn = op.get_bind()

    # 1) notifications 扩列
    _add_column_if_missing(conn, "notifications", sa.Column("read_at", sa.DateTime(timezone=True), nullable=True))
    _add_column_if_missing(conn, "notifications", sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True))

    # 2) 存量水位回填（语义等价）：水位行存在才回填
    if _has_table(conn, "notification_state") and _has_table(conn, "notifications"):
        conn.execute(
            sa.text(
                """
                UPDATE notifications
                SET read_at = created_at
                WHERE read_at IS NULL
                  AND id <= (
                      SELECT COALESCE(MAX(last_read_id), 0)
                      FROM notification_state WHERE id = 1
                  )
                """
            )
        )

    # 3) async_task_records 影子表
    if not _has_table(conn, "async_task_records"):
        op.create_table(
            "async_task_records",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("task_type", sa.String(32), nullable=False),
            sa.Column("task_id", sa.String(64), nullable=False),
            sa.Column("status", sa.String(32), nullable=False),
            sa.Column("name", sa.String(200), nullable=False, server_default=""),
            sa.Column("extra", sa.JSON, nullable=True),
            sa.Column("error", sa.Text, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_async_task_records_task_type", "async_task_records", ["task_type"])
        op.create_index("uq_async_task_records_task_id", "async_task_records", ["task_id"], unique=True)


def downgrade() -> None:
    conn = op.get_bind()
    if _has_table(conn, "async_task_records"):
        op.drop_index("uq_async_task_records_task_id", table_name="async_task_records")
        op.drop_index("ix_async_task_records_task_type", table_name="async_task_records")
        op.drop_table("async_task_records")
    # read_at/processed_at 不回滚：回滚会销毁升级后产生的逐行已读数据，
    # 列可空无害（旧代码路径不引用）
