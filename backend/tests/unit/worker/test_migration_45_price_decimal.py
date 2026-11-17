"""45 号迁移 + PriceAsFloat 价格列收口单测（P2-7）。

迁移部分同 test_migration_40 先例：不经 env.py（其 DB_FILE 全局 engine 指向生产
库文件），用 MigrationContext + Operations 手工驱动，验证 Float→DECIMAL(30,8)
原地改型保数据可幂等（交易台账不可丢弃，batch 重建必须拷贝数据）。
模型部分验证 PriceAsFloat 写入形态收口：float/str/Decimal 全部 float 读出，
数量×价格混算（models unrealized_pnl_pct 同款）不再有 Float/Decimal 二值风险。
"""

import importlib.util
from decimal import Decimal
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Numeric
from sqlalchemy.orm import Session

# worker/strategy 两个 mapper 模块先注册，避免全局 mapper configure 失败（同 test_kline_volume_decimal_migration）
import strategy.models
import worker.models
from worker.models import PriceAsFloat, WorkerPosition, WorkerTrade

_MIGRATION_PATH = Path(__file__).resolve().parents[3] / "alembic" / "versions" / "45_worker_price_columns_to_decimal.py"

# (表, 列)：与迁移 _PRICE_COLUMNS 一致
_LEGACY_DDL = {
    "worker_trades": "CREATE TABLE worker_trades (id INTEGER PRIMARY KEY, price FLOAT)",
    "worker_orders": "CREATE TABLE worker_orders (id INTEGER PRIMARY KEY, price FLOAT, avg_fill_price FLOAT)",
    "worker_positions": "CREATE TABLE worker_positions (id INTEGER PRIMARY KEY, entry_price FLOAT, current_price FLOAT)",
    "worker_fill_evidence": "CREATE TABLE worker_fill_evidence (id INTEGER PRIMARY KEY, price FLOAT)",
}


def _load_migration():
    spec = importlib.util.spec_from_file_location("migration_45", _MIGRATION_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _build_legacy_db(conn) -> None:
    """预置 44 时代的四表 Float 价格列 + float 二进制脏值。"""
    for ddl in _LEGACY_DDL.values():
        conn.execute(sa.text(ddl))
    # 0.1+0.2 的二进制误差代表历史 float 台账的脏精度
    dirty = 0.1 + 0.2
    conn.execute(sa.text("INSERT INTO worker_trades (price) VALUES (:p)"), {"p": dirty})
    conn.execute(sa.text("INSERT INTO worker_orders (price, avg_fill_price) VALUES (:p, :p)"), {"p": dirty})
    conn.execute(sa.text("INSERT INTO worker_positions (entry_price, current_price) VALUES (:p, :p)"), {"p": dirty})
    conn.execute(sa.text("INSERT INTO worker_fill_evidence (price) VALUES (:p)"), {"p": dirty})


def test_upgrade_converts_type_and_keeps_data() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        _build_legacy_db(conn)

    mod = _load_migration()
    for _ in range(2):  # 第二次跑验证幂等（重复 batch 重建不该炸）
        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                mod.upgrade()

    with engine.connect() as conn:
        inspector = sa.inspect(conn)
        for table, columns in {
            "worker_trades": ["price"],
            "worker_orders": ["price", "avg_fill_price"],
            "worker_positions": ["entry_price", "current_price"],
            "worker_fill_evidence": ["price"],
        }.items():
            types = {c["name"]: c["type"] for c in inspector.get_columns(table)}
            for col in columns:
                # Float 是 Numeric 子类，须同时排除 Float 才算真正迁移到 DECIMAL
                assert isinstance(types[col], Numeric) and not isinstance(types[col], sa.Float), (
                    f"{table}.{col} 应已是 DECIMAL: {types[col]}"
                )
        # 数据保留；DECIMAL(30,8) scale 截读后二进制脏值被规整为 0.3
        rows = conn.execute(sa.text("SELECT price FROM worker_trades")).fetchall()
        assert len(rows) == 1
        assert abs(float(rows[0][0]) - 0.3) < 1e-12


def test_upgrade_on_fresh_decimal_db_is_noop() -> None:
    """create_all 双通道场景：价格列已是 DECIMAL 时重跑 upgrade 不炸（幂等跳过）。"""
    engine = sa.create_engine("sqlite:///:memory:")
    mod = _load_migration()
    with engine.begin() as conn:
        for ddl in _LEGACY_DDL.values():
            conn.execute(sa.text(ddl.replace(" FLOAT", " NUMERIC(30, 8)")))
        for _ in range(2):
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                mod.upgrade()


def test_price_as_float_readout_types() -> None:
    """三种写入形态收口：float/str/Decimal 读出恒 float，DECIMAL(30,8) 精度落地。"""
    engine = sa.create_engine("sqlite:///:memory:")
    worker.models.Base.metadata.create_all(engine)
    with Session(engine) as session:
        # 0.1+0.2 float 直接写 -> bind 端 Decimal(str(...)) 保留字面精度
        session.add(
            WorkerTrade(
                worker_id=1,
                fill_id="f1",
                symbol="BTCUSDT",
                side="buy",
                order_type="market",
                quantity=0.1,
                price=0.1 + 0.2,
                notional=0.03,
            )
        )
        session.add(
            WorkerPosition(
                worker_id=1,
                position_id="p1",
                symbol="BTCUSDT",
                position_side="long",
                quantity=2.0,
                entry_price="123.45678901",
                status="OPEN",
            )
        )
        session.commit()

        trade = session.query(WorkerTrade).one()
        assert type(trade.price) is float
        assert repr(trade.price) == "0.3"  # DECIMAL(30,8) scale 截读清掉二进制尾数
        pos = session.query(WorkerPosition).one()
        assert type(pos.entry_price) is float
        assert repr(pos.entry_price) == "123.45678901"  # str 写入保真 9 位小数
        # 数量×价格混算（unrealized_pnl_pct 同款）不再 TypeError
        assert pos.to_dict()["unrealized_pnl_pct"] == 0


def test_price_column_not_float_for_gateway() -> None:
    """门禁同款判定：PriceAsFloat 列 isinstance(col.type, Float) 为 False。"""
    assert not isinstance(WorkerTrade.__table__.c.price.type, sa.Float)
    assert isinstance(WorkerTrade.__table__.c.price.type, PriceAsFloat)
