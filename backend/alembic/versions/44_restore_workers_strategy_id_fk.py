"""workers.strategy_id 外键物理修复（命名语义审计 P1-6）。

建模现状：ORM（worker/models.py `Worker.strategy_id`）与 API 层早已声明 strategy_id
FK + strategy_name 冗余回退字段，但历史迁移 8b8f30ec3699 重建 workers 表时把
ForeignKeyConstraint 错挂到过渡列 strategy_id_old 上，真正的 strategy_id 列裸奔——
SQLite 端物理 DDL 从此没有 FK（PRAGMA foreign_key_list 为空），走过同一路径的库
全部缺失。本迁移把 FK 补回 strategy_id 列，幂等可逆。

天花板（ponytail:）：SQLite 仅在连接开启 PRAGMA foreign_keys=ON 时才强制 FK，
本仓库主连接未开启（历史行为，保持不变以免牵连其它表），此修复在 SQLite 端是
结构性声明（对齐 ORM/PG、消除 create_all 与迁移路径的 schema 漂移），真正的引用
完整性仍由 service 层负责；PG 端修复后即为强约束。若未来要 SQLite 强制，应全库
校验孤儿数据后统一开启 pragma，而不是本迁移顺手开。

Revision ID: 44
Revises: 43
Create Date: 2026-11-17
"""

import sqlalchemy as sa

from alembic import op

revision = "44"
down_revision = "43"
branch_labels = None
depends_on = None

_TABLE = "workers"
_REFERRED = "strategies"
_FK_NAME = "fk_workers_strategy_id"


def _strategy_fk(conn) -> dict | None:
    """查找 workers 表指向 strategies.id 的 FK（按引用而非约束名判定，幂等）。"""
    for fk in sa.inspect(conn).get_foreign_keys(_TABLE):
        if fk["referred_table"] == _REFERRED and fk["constrained_columns"] == ["strategy_id"]:
            return fk
    return None


def upgrade() -> None:
    conn = op.get_bind()
    if _strategy_fk(conn) is not None:
        return  # FK 已存在（新库 create_all / 本迁移重放）则跳过
    if conn.dialect.name == "sqlite":
        # SQLite 无 ADD CONSTRAINT，只能整表重建；batch 模式自动反射并恢复全部列/索引
        with op.batch_alter_table(_TABLE) as batch_op:
            batch_op.create_foreign_key(_FK_NAME, _REFERRED, ["strategy_id"], ["id"])
    else:
        op.create_foreign_key(_FK_NAME, _TABLE, _REFERRED, ["strategy_id"], ["id"])


def downgrade() -> None:
    conn = op.get_bind()
    fk = _strategy_fk(conn)
    if fk is None:
        return
    if conn.dialect.name == "sqlite":
        # 本迁移创建的 FK 带确定名，batch 重建时反射得到同名约束才能按名删除
        with op.batch_alter_table(_TABLE) as batch_op:
            batch_op.drop_constraint(fk["name"] or _FK_NAME, type_="foreignkey")
    else:
        op.drop_constraint(fk["name"] or _FK_NAME, _TABLE, type_="foreignkey")
