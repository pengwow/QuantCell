"""remove system_logs table

Migration to remove the system_logs table as logging has been migrated
to a file-based system (utils/file_log_manager.py).

Revision ID: 9_remove_system_logs_table
Revises: 8_add_system_logs_table
Create Date: 2026-04-29 15:00:00.000000

"""

from typing import TYPE_CHECKING

import sqlalchemy as sa

from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "9_remove_system_logs_table"
down_revision: str | None = "8_add_system_logs_table"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# 本库历史上有两种建表路径：alembic 增量、或应用启动时 create_all + 版本直标 head
# （后者导致祖先链里的 8 号"已应用"实则从未建表）。drop 做存在性守卫，
# 保证两条路径下 21→head 补跑本迁移都不会因表/索引缺失而失败。
def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _log_indexes() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if "system_logs" not in inspector.get_table_names():
        return set()
    return {ix["name"] for ix in inspector.get_indexes("system_logs")}


def upgrade() -> None:
    """
    升级数据库：删除system_logs表

    日志功能已迁移到基于文件的日志系统，不再需要此表。
    """
    # 删除复合索引
    present = _log_indexes()
    for index_name in (
        "idx_system_logs_module_timestamp",
        "idx_system_logs_type_timestamp",
        "idx_system_logs_level_timestamp",
        # 删除单列索引
        "ix_system_logs_created_at",
        "ix_system_logs_module",
        "ix_system_logs_trace_id",
        "ix_system_logs_logger_name",
        "ix_system_logs_log_type",
        "ix_system_logs_level",
        "ix_system_logs_timestamp",
        "ix_system_logs_id",
    ):
        if index_name in present:
            op.drop_index(index_name, table_name="system_logs")

    # 删除表
    if "system_logs" in _tables():
        op.drop_table("system_logs")


def downgrade() -> None:
    """
    降级数据库：重新创建system_logs表（如果需要回滚）

    警告：降级后表将为空，历史日志数据不会恢复。
    如需保留历史数据，请在升级前进行备份。
    """
    import sqlalchemy as sa

    # 创建system_logs表
    op.create_table(
        "system_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("level", sa.String(length=20), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("module", sa.String(length=200), nullable=True),
        sa.Column("function", sa.String(length=200), nullable=True),
        sa.Column("line", sa.Integer(), nullable=True),
        sa.Column("logger_name", sa.String(length=200), nullable=True),
        sa.Column("log_type", sa.String(length=50), nullable=False),
        sa.Column("extra_data", sa.Text(), nullable=True),
        sa.Column("exception_info", sa.Text(), nullable=True),
        sa.Column("trace_id", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # 创建索引
    op.create_index("ix_system_logs_id", "system_logs", ["id"], unique=False)
    op.create_index("ix_system_logs_timestamp", "system_logs", ["timestamp"], unique=False)
    op.create_index("ix_system_logs_level", "system_logs", ["level"], unique=False)
    op.create_index("ix_system_logs_log_type", "system_logs", ["log_type"], unique=False)
    op.create_index("ix_system_logs_logger_name", "system_logs", ["logger_name"], unique=False)
    op.create_index("ix_system_logs_trace_id", "system_logs", ["trace_id"], unique=False)
    op.create_index("ix_system_logs_module", "system_logs", ["module"], unique=False)
    op.create_index("ix_system_logs_created_at", "system_logs", ["created_at"], unique=False)

    # 创建复合索引
    op.create_index(
        "idx_system_logs_level_timestamp",
        "system_logs",
        ["level", "timestamp"],
        unique=False,
    )
    op.create_index(
        "idx_system_logs_type_timestamp",
        "system_logs",
        ["log_type", "timestamp"],
        unique=False,
    )
    op.create_index(
        "idx_system_logs_module_timestamp",
        "system_logs",
        ["module", "timestamp"],
        unique=False,
    )
