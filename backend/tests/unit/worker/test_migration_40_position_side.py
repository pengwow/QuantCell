"""40 号迁移幂等单测。

不经 env.py（其内部 DB_FILE 全局 engine 指向生产库文件），改用
MigrationContext + Operations 手工驱动迁移模块：Operations.__init__ 会注册
全局 alembic.op 代理，迁移模块内的 op.xxx 调用由此路由。对同一内存库连跑
两次 upgrade 验证幂等（重复 ALTER/RENAME 必炸，guard 缺失会当场暴露）。
"""

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

_MIGRATION_PATH = Path(__file__).resolve().parents[3] / "alembic" / "versions" / "40_add_position_side_reduce_only.py"


def _load_migration():
    spec = importlib.util.spec_from_file_location("migration_40", _MIGRATION_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _build_legacy_db(conn) -> None:
    """预置 39 时代的三张表 + 脏大写数据。"""
    conn.execute(sa.text("CREATE TABLE worker_orders (id INTEGER PRIMARY KEY, side TEXT)"))
    conn.execute(sa.text("CREATE TABLE worker_trades (id INTEGER PRIMARY KEY, side TEXT)"))
    conn.execute(sa.text("CREATE TABLE worker_positions (id INTEGER PRIMARY KEY, side TEXT)"))
    conn.execute(sa.text("INSERT INTO worker_orders (side) VALUES ('BUY'), ('SELL'), ('Buy')"))
    conn.execute(sa.text("INSERT INTO worker_positions (side) VALUES ('LONG'), ('SHORT')"))


def test_upgrade_idempotent_and_normalizes() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        _build_legacy_db(conn)

    mod = _load_migration()
    for _ in range(2):  # 第二次跑验证幂等
        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                mod.upgrade()

    with engine.connect() as conn:
        # orders：加了两列 + 存量大写归一
        order_cols = {c["name"] for c in sa.inspect(conn).get_columns("worker_orders")}
        assert {"position_side", "reduce_only"} <= order_cols
        sides = [r[0] for r in conn.execute(sa.text("SELECT side FROM worker_orders ORDER BY id"))]
        assert sides == ["buy", "sell", "buy"]
        fill_defaults = conn.execute(sa.text("SELECT position_side, reduce_only FROM worker_orders")).fetchall()
        assert all(ps == "both" and ro == 0 for ps, ro in fill_defaults)

        # positions：列已改名 + 小写化
        pos_cols = {c["name"] for c in sa.inspect(conn).get_columns("worker_positions")}
        assert "position_side" in pos_cols and "side" not in pos_cols
        pos = [r[0] for r in conn.execute(sa.text("SELECT position_side FROM worker_positions ORDER BY id"))]
        assert pos == ["long", "short"]

        # trades：加列不动 side
        trade_cols = {c["name"] for c in sa.inspect(conn).get_columns("worker_trades")}
        assert {"position_side", "reduce_only"} <= trade_cols


def test_upgrade_on_fresh_canonical_db_is_noop() -> None:
    """create_all 双通道场景：目标 schema 已存在时重跑 upgrade 不炸不重复加列。"""
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        _build_legacy_db(conn)

    mod = _load_migration()
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            mod.upgrade()

    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            mod.upgrade()  # 第二次必须 no-op 成功
