"""add_factor_mining_events

factor_mining_runs 增加 events_json：持久化 LLM 挖掘过程事件（最新 500 条），
历史详情可回看，中断时可定位最后卡点。

Revision ID: 19
Revises: 18
Create Date: 2026-10-09 00:00:00.000000
"""

from typing import TYPE_CHECKING

import sqlalchemy as sa

from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "19"
down_revision: str | Sequence[str] | None = "18"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """factor_mining_runs 增加 events_json：过程事件 JSON 数组（最新 500 条）"""
    op.add_column("factor_mining_runs", sa.Column("events_json", sa.Text(), nullable=True))


def downgrade() -> None:
    """回滚：删除 events_json 列"""
    op.drop_column("factor_mining_runs", "events_json")
