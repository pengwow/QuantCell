"""add_research_sessions_trials_knowledge

研究模块 P0 三张表（PRD §7）：
- research_sessions：会话与成本/进度汇总
- research_trials：候选试验与决策硬门结果
- research_knowledge：失败签名库（P0 仅落表，P1 启用短路）

Revision ID: 22
Revises: 21
Create Date: 2026-11-04 00:00:00.000000
"""

from typing import TYPE_CHECKING

import sqlalchemy as sa

from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "22"
down_revision: str | Sequence[str] | None = "21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# 本项目的既有约定："create_all 是 schema 真相源，alembic 只负责增量补丁"。
# 部分真实库曾由应用启动时的 create_all 抢先建出 research 表，但 alembic 版本
# 仍停在 21；这里对 upgrade 做存在性守卫，命中已有的表/索引时跳过建，
# 让这类库能平滑升到 head。全新空库不受影响（都不存在，全部新建）。
def _tables_present() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _index_names(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    try:
        return {ix["name"] for ix in inspector.get_indexes(table)}
    except sa.exc.NoSuchTableError:
        return set()


def _add_index(name: str, table: str, cols: list[str], unique: bool = False) -> None:
    if name not in _index_names(table):
        op.create_index(name, table, cols, unique=unique)


def upgrade() -> None:
    """创建研究会话 / 试验 / 知识三张表（幂等：已存在则跳过）"""
    tables = _tables_present()
    if "research_sessions" not in tables:
        op.create_table(
            "research_sessions",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("owner_id", sa.String(length=64), nullable=False),
            sa.Column("name", sa.String(length=64), nullable=False, server_default=""),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
            sa.Column("mode", sa.String(length=8), nullable=False, server_default="deep"),
            sa.Column("n_candidates", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("backend_job_id", sa.String(length=64), nullable=True),
            sa.Column("config_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("best_trial_id", sa.Integer(), nullable=True),
            sa.Column("loop_done", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("step_idx", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("token_used", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("llm_calls", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("request_id", sa.String(length=64), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("extended_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        )
    _add_index("ix_research_sessions_owner_created", "research_sessions", ["owner_id", "created_at"])
    _add_index("ix_research_sessions_status", "research_sessions", ["status"])
    _add_index("ix_research_sessions_mode", "research_sessions", ["mode"])

    if "research_trials" not in tables:
        op.create_table(
            "research_trials",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "session_id",
                sa.Integer(),
                sa.ForeignKey("research_sessions.id"),
                nullable=False,
            ),
            sa.Column("loop_idx", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("candidate_idx", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="planned"),
            sa.Column("hypothesis", sa.Text(), nullable=True),
            sa.Column("task_json", sa.Text(), nullable=True),
            sa.Column("code", sa.Text(), nullable=True),
            sa.Column("code_hash", sa.String(length=64), nullable=True),
            sa.Column("metrics_json", sa.Text(), nullable=True),
            sa.Column("oos_flag", sa.String(length=16), nullable=True),
            sa.Column("feedback_json", sa.Text(), nullable=True),
            sa.Column("judge_json", sa.Text(), nullable=True),
            sa.Column("decision", sa.Boolean(), nullable=True),
            sa.Column("promoted_factor_name", sa.String(length=128), nullable=True),
            sa.Column("quick_run_id", sa.String(length=36), nullable=True),
            sa.Column("parent_trial_id", sa.Integer(), nullable=True),
            sa.Column("replay_of_id", sa.Integer(), nullable=True),
            sa.Column("token_used", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("llm_calls", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("exception", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        )
    # session_loop 索引迁移到 23 时会被重建为 unique，这里保持普通索引口径
    _add_index("ix_research_trials_session_loop", "research_trials", ["session_id", "loop_idx", "candidate_idx"])
    _add_index("ix_research_trials_status", "research_trials", ["status"])
    _add_index("ix_research_trials_code_hash", "research_trials", ["code_hash"])
    _add_index("ix_research_trials_quick_run_id", "research_trials", ["quick_run_id"])

    if "research_knowledge" not in tables:
        op.create_table(
            "research_knowledge",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("owner_id", sa.String(length=64), nullable=True),
            sa.Column("session_id", sa.Integer(), nullable=True),
            sa.Column("trial_id", sa.Integer(), nullable=True),
            sa.Column("kind", sa.String(length=32), nullable=False, server_default="failure"),
            sa.Column("signature", sa.String(length=255), nullable=False),
            sa.Column("payload_json", sa.Text(), nullable=True),
            sa.Column("hit_count", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        )
    _add_index("ix_research_knowledge_signature", "research_knowledge", ["signature"])
    _add_index("ix_research_knowledge_owner_kind", "research_knowledge", ["owner_id", "kind"])


def downgrade() -> None:
    """按依赖倒序删除（downgrade 面向迁移自建的库，保持确定性 drop）"""
    _drop_index_of("ix_research_knowledge_owner_kind", "research_knowledge")
    _drop_index_of("ix_research_knowledge_signature", "research_knowledge")
    _drop_table("research_knowledge")

    _drop_index_of("ix_research_trials_quick_run_id", "research_trials")
    _drop_index_of("ix_research_trials_code_hash", "research_trials")
    _drop_index_of("ix_research_trials_status", "research_trials")
    _drop_index_of("ix_research_trials_session_loop", "research_trials")
    _drop_table("research_trials")

    _drop_index_of("ix_research_sessions_mode", "research_sessions")
    _drop_index_of("ix_research_sessions_status", "research_sessions")
    _drop_index_of("ix_research_sessions_owner_created", "research_sessions")
    _drop_table("research_sessions")


def _drop_index_of(name: str, table: str) -> None:
    if name in _index_names(table):
        op.drop_index(name, table_name=table)


def _drop_table(name: str) -> None:
    if name in _tables_present():
        op.drop_table(name)
