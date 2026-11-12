"""Agent Token 与工具调用审计表（P2-06）。

agent_tokens 存 sha256 摘要（明文只出现一次），scope read/write 控制工具副作用
许可；agent_tool_audit 记录每次工具调用的参数摘要与脱敏 JSON，供安全追溯。
本迁移 down 指向 35。

Revision ID: 36
Revises: 35
Create Date: 2026-11-12
"""

import sqlalchemy as sa

from alembic import op

revision = "36"
down_revision = "35"
branch_labels = None
depends_on = None


def _existing_tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    # 幂等：create_all 双通道建过的存量库直接跳过
    tables = _existing_tables()
    if "agent_tokens" not in tables:
        op.create_table(
            "agent_tokens",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
            sa.Column("scope", sa.String(20), nullable=False, server_default="read"),
            sa.Column("expires_at", sa.DateTime(), nullable=True),
            sa.Column("last_used_at", sa.DateTime(), nullable=True),
            sa.Column("use_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("revoked_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_agent_tokens_id", "agent_tokens", ["id"])
        op.create_index("ix_agent_tokens_token_hash", "agent_tokens", ["token_hash"])
        op.create_index("ix_agent_tokens_scope", "agent_tokens", ["scope"])
    if "agent_tool_audit" not in tables:
        op.create_table(
            "agent_tool_audit",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tool", sa.String(100), nullable=False),
            sa.Column("args_hash", sa.String(64), nullable=True),
            sa.Column("args_redacted", sa.Text(), nullable=True),
            sa.Column("result_status", sa.String(20), nullable=False, server_default="success"),
            sa.Column("user", sa.String(100), nullable=True),
            sa.Column("token", sa.String(50), nullable=True),
            sa.Column("duration_ms", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_agent_tool_audit_id", "agent_tool_audit", ["id"])
        op.create_index("ix_agent_tool_audit_tool", "agent_tool_audit", ["tool"])
        op.create_index("ix_agent_tool_audit_result_status", "agent_tool_audit", ["result_status"])


def downgrade() -> None:
    tables = _existing_tables()
    if "agent_tool_audit" in tables:
        op.drop_index("ix_agent_tool_audit_result_status", table_name="agent_tool_audit")
        op.drop_index("ix_agent_tool_audit_tool", table_name="agent_tool_audit")
        op.drop_index("ix_agent_tool_audit_id", table_name="agent_tool_audit")
        op.drop_table("agent_tool_audit")
    if "agent_tokens" in tables:
        op.drop_index("ix_agent_tokens_scope", table_name="agent_tokens")
        op.drop_index("ix_agent_tokens_token_hash", table_name="agent_tokens")
        op.drop_index("ix_agent_tokens_id", table_name="agent_tokens")
        op.drop_table("agent_tokens")
