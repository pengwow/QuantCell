"""合并研究模块与 system_logs 分支的两个 head。

背景：仓库历史上有两条互不相交的迁移链——
- 主链：… → 21_add_research_session → 22_add_research_tables → 23_add_research_scenario
- 日志链：… → 8_add_system_logs_table → 9_remove_system_logs_table
两者都从 8_add_system_logs_table 分叉，导致 `alembic upgrade head` 报 Multiple heads。
本迁移只做合并，不改动任何既有迁移的内容。

Revision ID: 24
Revises: 23, 9_remove_system_logs_table
Create Date: 2026-11-04
"""

revision = "24"
down_revision = ("23", "9_remove_system_logs_table")
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 纯合并节点，无 schema 变更
    pass


def downgrade() -> None:
    pass
