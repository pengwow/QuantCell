"""工人属地（P1-07）：workers 表加 owner_id 归属列。

owner_id = 创建者 JWT sub（nullable）：可空表示无归属（历史数据/单用户模式，
语义与现状一致）。RBAC 权限枚举 enforcement（rbac.enforcement_enabled）开启后，
可基于该字段做资源归属判定。

33 号迁移被 P1-02/03 预留后确认空缺（相关迁移动作并入 30-32），按实施设计
"§7 迁移版本号分配表"约定：33 空缺则本迁移 down 指向 32。

Revision ID: 34
Revises: 32
Create Date: 2026-11-12
"""

import sqlalchemy as sa

from alembic import op

revision = "34"
down_revision = "32"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    insp = sa.inspect(op.get_bind())
    return column in [c["name"] for c in insp.get_columns(table)]


def upgrade() -> None:
    # 幂等：create_all 双通道建过的存量库直接跳过
    if _column_exists("workers", "owner_id"):
        return
    # nullable 不带外键：JWT sub 与 users 表 ID 的对应由应用层维护，
    # 历史数据统一为 NULL（无归属），避免迁移期强制回填造成错误归属
    op.add_column("workers", sa.Column("owner_id", sa.Integer(), nullable=True))
    op.create_index("ix_workers_owner_id", "workers", ["owner_id"])


def downgrade() -> None:
    if _column_exists("workers", "owner_id"):
        op.drop_index("ix_workers_owner_id", table_name="workers")
        op.drop_column("workers", "owner_id")
