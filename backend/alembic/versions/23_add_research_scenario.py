"""add_research_scenario_and_prd_fields

P0.5 / PRD v0.3 数据模型补齐：
- research_sessions 增加 scenario（factor/model/strategy，P0 仅 factor 有实现）
- research_trials 补齐 PRD §7.2 字段：metrics_oos_json / oos_note /
  hypothesis_reason / hypothesis_prediction / model / prompt_hash / temperature / duration_ms
- quick_run_id 由 str(36) 改为 Integer，与 factor_mining_runs.id 主键类型对齐
  （P0 该列从未写值，直接重建列不丢数据）
- (session_id, loop_idx, candidate_idx) 由普通索引改为唯一索引，供续跑去重

Revision ID: 23
Revises: 22
Create Date: 2026-11-04 00:00:01.000000
"""

from typing import TYPE_CHECKING

import sqlalchemy as sa

from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "23"
down_revision: str | Sequence[str] | None = "22"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# 与 22 号迁移同理：部分库的表由 create_all 抢先建成（含 23 版结构），
# 版本却停在 22，upgrade 做存在性守卫后可平滑通过（详见 22 号迁移注释）。
def _columns(table: str) -> dict[str, sa.types.TypeEngine]:
    inspector = sa.inspect(op.get_bind())
    try:
        return {col["name"]: col["type"] for col in inspector.get_columns(table)}
    except sa.exc.NoSuchTableError:
        return {}


def _index_names(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    try:
        return {ix["name"] for ix in inspector.get_indexes(table)}
    except sa.exc.NoSuchTableError:
        return set()


def _add_column_if_missing(table: str, column: sa.Column) -> None:
    if column.name not in _columns(table):
        op.add_column(table, column)


def _drop_index_if_exists(name: str, table: str) -> None:
    if name in _index_names(table):
        op.drop_index(name, table_name=table)


def upgrade() -> None:
    """补齐 scenario 与 PRD 字段（幂等：已存在则跳过）"""
    _add_column_if_missing(
        "research_sessions",
        sa.Column("scenario", sa.String(length=12), nullable=False, server_default="factor"),
    )
    if "ix_research_sessions_scenario" not in _index_names("research_sessions"):
        op.create_index("ix_research_sessions_scenario", "research_sessions", ["scenario"])

    for column in (
        sa.Column("metrics_oos_json", sa.Text(), nullable=True),
        sa.Column("oos_note", sa.Text(), nullable=True),
        sa.Column("hypothesis_reason", sa.Text(), nullable=True),
        sa.Column("hypothesis_prediction", sa.Text(), nullable=True),
        sa.Column("model", sa.String(length=64), nullable=True),
        sa.Column("prompt_hash", sa.String(length=64), nullable=True),
        sa.Column("temperature", sa.Float(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
    ):
        _add_column_if_missing("research_trials", column)

    # quick_run_id：String(36) → Integer（SQLite 用重建列实现，P0 无存量值）。
    # 已是 INTEGER 类型的库（create_all 按 23 版 ORM 建表）跳过重建。
    current_type = str(_columns("research_trials").get("quick_run_id", "")).upper()
    if not current_type.startswith("INTEGER"):
        _drop_index_if_exists("ix_research_trials_quick_run_id", "research_trials")
        if "quick_run_id" in _columns("research_trials"):
            op.drop_column("research_trials", "quick_run_id")
        op.add_column("research_trials", sa.Column("quick_run_id", sa.Integer(), nullable=True))
        op.create_index(
            "ix_research_trials_quick_run_id",
            "research_trials",
            ["quick_run_id"],
        )

    # 续跑去重：同一 (session, loop, candidate) 只允许一条 trial
    _drop_index_if_exists("ix_research_trials_session_loop", "research_trials")
    if "ix_research_trials_session_loop" not in _index_names("research_trials"):
        op.create_index(
            "ix_research_trials_session_loop",
            "research_trials",
            ["session_id", "loop_idx", "candidate_idx"],
            unique=True,
        )


def downgrade() -> None:
    """回滚到 22（quick_run_id 退回字符串，唯一索引退回普通索引）"""
    _drop_index_if_exists("ix_research_trials_session_loop", "research_trials")
    if "ix_research_trials_session_loop" not in _index_names("research_trials"):
        op.create_index(
            "ix_research_trials_session_loop",
            "research_trials",
            ["session_id", "loop_idx", "candidate_idx"],
        )

    _drop_index_if_exists("ix_research_trials_quick_run_id", "research_trials")
    current_type = str(_columns("research_trials").get("quick_run_id", "")).upper()
    if "quick_run_id" in _columns("research_trials") and not current_type.startswith("VARCHAR"):
        op.drop_column("research_trials", "quick_run_id")
    _add_column_if_missing("research_trials", sa.Column("quick_run_id", sa.String(length=36), nullable=True))
    if "ix_research_trials_quick_run_id" not in _index_names("research_trials"):
        op.create_index("ix_research_trials_quick_run_id", "research_trials", ["quick_run_id"])

    for column in (
        "duration_ms",
        "temperature",
        "prompt_hash",
        "model",
        "hypothesis_prediction",
        "hypothesis_reason",
        "oos_note",
        "metrics_oos_json",
    ):
        if column in _columns("research_trials"):
            op.drop_column("research_trials", column)

    if "ix_research_sessions_scenario" in _index_names("research_sessions"):
        op.drop_index("ix_research_sessions_scenario", table_name="research_sessions")
    if "scenario" in _columns("research_sessions"):
        op.drop_column("research_sessions", "scenario")
