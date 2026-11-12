"""指标信号提醒规则表（P2-07）。

indicator_alert_rules 存储指标信号提醒规则：标的/周期/条件/通知渠道/去重窗口，
评估与投递逻辑见 backend/indicators/alerts.py 与 alerts_routes.py。
本迁移 down 指向 36。

Revision ID: 37
Revises: 36
Create Date: 2026-11-12
"""

import sqlalchemy as sa

from alembic import op

revision = "37"
down_revision = "36"
branch_labels = None
depends_on = None


def _existing_tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    # 幂等：create_all 双通道建过的存量库直接跳过
    if "indicator_alert_rules" in _existing_tables():
        return
    op.create_table(
        "indicator_alert_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("indicator_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=True),
        sa.Column("symbol", sa.String(50), nullable=False),
        sa.Column("period", sa.String(20), nullable=False, server_default="1h"),
        sa.Column("market_type", sa.String(20), nullable=False, server_default="crypto"),
        sa.Column("crypto_type", sa.String(20), nullable=False, server_default="spot"),
        sa.Column("params", sa.Text(), nullable=True),
        sa.Column("plot_name", sa.String(100), nullable=True),
        sa.Column("op", sa.String(20), nullable=False, server_default="gt"),
        sa.Column("threshold", sa.Numeric(24, 10), nullable=True, server_default="0"),
        sa.Column("channels", sa.Text(), nullable=True),
        sa.Column("frequency", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("last_fired_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_indicator_alert_rules_id", "indicator_alert_rules", ["id"])
    op.create_index("ix_indicator_alert_rules_indicator_id", "indicator_alert_rules", ["indicator_id"])


def downgrade() -> None:
    tables = _existing_tables()
    if "indicator_alert_rules" in tables:
        op.drop_index("ix_indicator_alert_rules_indicator_id", table_name="indicator_alert_rules")
        op.drop_index("ix_indicator_alert_rules_id", table_name="indicator_alert_rules")
        op.drop_table("indicator_alert_rules")
