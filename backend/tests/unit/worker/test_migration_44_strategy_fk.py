"""44 号迁移幂等单测：workers.strategy_id 物理 FK 修复。

复刻 test_migration_40_position_side 的手工驱动模式（MigrationContext +
Operations.context，绕开 env.py 的全局生产 engine）：构造 8b8f30ec3699 重建后的
坏 DDL（strategy_id 无 FK、同行仍有 strategy_name），验证
upgrade × 2 幂等 / FK 已存在时 no-op / downgrade 可逆。
"""

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

_MIGRATION_PATH = Path(__file__).resolve().parents[3] / "alembic" / "versions" / "44_restore_workers_strategy_id_fk.py"


def _load_migration():
    spec = importlib.util.spec_from_file_location("migration_44", _MIGRATION_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _build_broken_db(conn) -> None:
    """复刻 8b8f30ec3699 重建后的物理 DDL：strategy_id 无任何 FK 约束。"""
    conn.execute(sa.text("CREATE TABLE strategies (id INTEGER PRIMARY KEY, name TEXT)"))
    conn.execute(
        sa.text(
            "CREATE TABLE workers ("
            "id INTEGER PRIMARY KEY, "
            "name TEXT NOT NULL, "
            "strategy_id INTEGER, "  # 历史重建 bug：裸列
            "strategy_name TEXT"
            ")"
        )
    )
    conn.execute(sa.text("INSERT INTO strategies (id, name) VALUES (1, 'dual_ma')"))
    conn.execute(sa.text("INSERT INTO workers (id, name, strategy_id, strategy_name) VALUES (1, 'w1', 1, 'dual_ma')"))


def _upgrade(engine) -> None:
    mod = _load_migration()
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            mod.upgrade()


def _strategy_fks(engine) -> list:
    with engine.connect() as conn:
        return conn.execute(sa.text("PRAGMA foreign_key_list(workers)")).fetchall()


def test_upgrade_adds_fk_and_is_idempotent() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        _build_broken_db(conn)
    assert _strategy_fks(engine) == []  # 前置：坏 DDL 确无 FK

    mod = _load_migration()
    for _ in range(2):  # 第二次 verifying 幂等（batch 重建重复跑必须 no-op）
        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                mod.upgrade()

    fks = _strategy_fks(engine)
    assert [(f[3], f[2]) for f in fks] == [("strategy_id", "strategies")]  # (from, referred_table)
    # 列与数据在 batch 重建后保留
    with engine.connect() as conn:
        rows = conn.execute(sa.text("SELECT id, name, strategy_id, strategy_name FROM workers")).fetchall()
    assert rows == [(1, "w1", 1, "dual_ma")]


def test_upgrade_on_fk_ready_db_is_noop() -> None:
    """create_all 双通道：目标 schema 带着 FK 跑过本迁移时重放不炸不重复加约束。"""
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        _build_broken_db(conn)

    _upgrade(engine)
    count_before = len(_strategy_fks(engine))

    _upgrade(engine)  # FK 已存在 → guard 命中 no-op
    assert len(_strategy_fks(engine)) == count_before


def test_downgrade_removes_fk_and_upgrade_restores() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        _build_broken_db(conn)
    _upgrade(engine)
    assert len(_strategy_fks(engine)) == 1

    mod = _load_migration()
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            mod.downgrade()

    assert _strategy_fks(engine) == []
    _upgrade(engine)  # 降级后再升回，FK 必须能重建
    assert len(_strategy_fks(engine)) == 1
