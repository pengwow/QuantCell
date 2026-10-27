"""add_worker_risk_control_runtime

worker_risk_control 运行时人工风控列：enabled 总开关（前端开关 + 实时生效链路）
+ 引擎热更新增三键（max_drawdown / max_leverage / circuit_breaker_cooldown_secs）。
存量「有效配置」行（原四活跃列任一非零）回填 enabled=1，保持既有风控行为不丢。

Revision ID: 20
Revises: 19
Create Date: 2026-10-27 00:00:00.000000
"""

from typing import TYPE_CHECKING

import sqlalchemy as sa

from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "20"
down_revision: str | Sequence[str] | None = "19"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """新增 enabled 总开关（NOT NULL default false）+ 3 个引擎热更新键，回填存量"""
    op.add_column(
        "worker_risk_control",
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false(), comment="人工风控总开关"),
    )
    op.add_column(
        "worker_risk_control",
        sa.Column("max_drawdown", sa.Float(), nullable=True, comment="最大回撤比例 (0,1]"),
    )
    op.add_column(
        "worker_risk_control",
        sa.Column("max_leverage", sa.Float(), nullable=True, comment="最大杠杆 [1,200]"),
    )
    op.add_column(
        "worker_risk_control",
        sa.Column("circuit_breaker_cooldown_secs", sa.Integer(), nullable=True, comment="熔断冷却秒数 [0,604800]"),
    )
    # 存量回填：原四活跃列任一非零视为用户配置过风控 → 人工开关打开
    op.execute(
        "UPDATE worker_risk_control SET enabled = 1 WHERE "
        "COALESCE(max_position_size, 0) > 0 OR COALESCE(max_position_pct, 0) > 0 OR "
        "COALESCE(daily_loss_limit, 0) > 0 OR COALESCE(daily_loss_amount, 0) > 0"
    )


def downgrade() -> None:
    """回滚：删除 4 个新列"""
    op.drop_column("worker_risk_control", "circuit_breaker_cooldown_secs")
    op.drop_column("worker_risk_control", "max_leverage")
    op.drop_column("worker_risk_control", "max_drawdown")
    op.drop_column("worker_risk_control", "enabled")
