"""47 号迁移 + 数量/资金账务列收口单测（P2-12）。

迁移部分同 test_migration_45 先例：不经 env.py（其 DB_FILE 全局 engine 指向生产
库文件），用 MigrationContext + Operations 手工驱动，验证 Float→DECIMAL(30,8)
原地改型保数据可幂等（交易台账不可丢弃，batch 重建必须拷贝数据）。
模型部分验证数量/资金族复用 PriceAsFloat 后的三态写入收口：float/str/Decimal
全部 float 读出，quantity×price 混算（to_dict unrealized_pnl_pct 同款）无二值风险。
"""

import importlib.util
from decimal import Decimal
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Numeric
from sqlalchemy.orm import Session

# worker/strategy 两个 mapper 模块先注册，避免全局 mapper configure 失败（同 test_migration_45）
import strategy.models
import worker.models
from worker.models import PriceAsFloat, WorkerCapital, WorkerOrder, WorkerPosition, WorkerTrade

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[3] / "alembic" / "versions" / "47_worker_quantity_columns_to_decimal.py"
)

# (表, 列)：与迁移 _MONEY_COLUMNS 一致，legacy DDL 按表列齐数量/资金列
_LEGACY_DDL = {
    "worker_trades": "CREATE TABLE worker_trades (id INTEGER PRIMARY KEY, quantity FLOAT, notional FLOAT, fee FLOAT, realized_pnl FLOAT)",
    "worker_orders": "CREATE TABLE worker_orders (id INTEGER PRIMARY KEY, quantity FLOAT, filled_quantity FLOAT)",
    "worker_positions": "CREATE TABLE worker_positions (id INTEGER PRIMARY KEY, quantity FLOAT, unrealized_pnl FLOAT, realized_pnl FLOAT, margin_used FLOAT)",
    "worker_fill_evidence": "CREATE TABLE worker_fill_evidence (id INTEGER PRIMARY KEY, quantity FLOAT, fee FLOAT)",
    "worker_capital": "CREATE TABLE worker_capital (id INTEGER PRIMARY KEY, initial_capital FLOAT, current_capital FLOAT, available_capital FLOAT, frozen_capital FLOAT, margin_used FLOAT)",
}

# 与迁移 _MONEY_COLUMNS 完全一致的期望清单（迁移后逐列断言 DECIMAL）
_EXPECTED = {
    "worker_trades": ["quantity", "notional", "fee", "realized_pnl"],
    "worker_orders": ["quantity", "filled_quantity"],
    "worker_positions": ["quantity", "unrealized_pnl", "realized_pnl", "margin_used"],
    "worker_fill_evidence": ["quantity", "fee"],
    "worker_capital": ["initial_capital", "current_capital", "available_capital", "frozen_capital", "margin_used"],
}


def _load_migration():
    spec = importlib.util.spec_from_file_location("migration_47", _MIGRATION_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _build_legacy_db(conn) -> None:
    """预置 46 时代的五表 Float 账务列 + float 二进制脏值。"""
    for ddl in _LEGACY_DDL.values():
        conn.execute(sa.text(ddl))
    # 0.1+0.2 的二进制误差代表历史 float 台账的脏精度
    dirty = 0.1 + 0.2
    conn.execute(
        sa.text("INSERT INTO worker_trades (quantity, notional, fee, realized_pnl) VALUES (:p, :p, :p, :p)"),
        {"p": dirty},
    )
    conn.execute(sa.text("INSERT INTO worker_orders (quantity, filled_quantity) VALUES (:p, :p)"), {"p": dirty})
    conn.execute(
        sa.text(
            "INSERT INTO worker_positions (quantity, unrealized_pnl, realized_pnl, margin_used) VALUES (:p, :p, :p, :p)"
        ),
        {"p": dirty},
    )
    conn.execute(sa.text("INSERT INTO worker_fill_evidence (quantity, fee) VALUES (:p, :p)"), {"p": dirty})
    conn.execute(
        sa.text(
            "INSERT INTO worker_capital (initial_capital, current_capital, available_capital, frozen_capital, margin_used)"
            " VALUES (:p, :p, :p, :p, :p)"
        ),
        {"p": dirty},
    )


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
        for table, columns in _EXPECTED.items():
            types = {c["name"]: c["type"] for c in inspector.get_columns(table)}
            for col in columns:
                # Float 是 Numeric 子类，须同时排除 Float 才算真正迁移到 DECIMAL
                assert isinstance(types[col], Numeric) and not isinstance(types[col], sa.Float), (
                    f"{table}.{col} 应已是 DECIMAL: {types[col]}"
                )
        # 数据保留；DECIMAL(30,8) scale 截读后二进制脏值被规整为 0.3
        trade_rows = conn.execute(sa.text("SELECT quantity, fee FROM worker_trades")).fetchall()
        assert len(trade_rows) == 1
        assert abs(float(trade_rows[0][0]) - 0.3) < 1e-12


def test_upgrade_on_fresh_decimal_db_is_noop() -> None:
    """create_all 双通道场景：账务列已是 DECIMAL 时重跑 upgrade 不炸（幂等跳过）。"""
    engine = sa.create_engine("sqlite:///:memory:")
    mod = _load_migration()
    with engine.begin() as conn:
        for ddl in _LEGACY_DDL.values():
            conn.execute(sa.text(ddl.replace(" FLOAT", " NUMERIC(30, 8)")))
        for _ in range(2):
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                mod.upgrade()


def test_money_columns_readout_types() -> None:
    """数量/资金族三种写入形态收口：float/str/Decimal 读出恒 float，DECIMAL(30,8) 精度落地。"""
    engine = sa.create_engine("sqlite:///:memory:")
    worker.models.Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            WorkerTrade(
                worker_id=1,
                fill_id="f1",
                symbol="BTCUSDT",
                side="buy",
                order_type="market",
                quantity="0.12345678",  # str 写入保真 8 位小数
                price=100.0,
                notional=0.1 + 0.2,  # float 直接写 -> bind 端 Decimal(str(...)) 保留字面精度
                fee=Decimal("0.001"),
                realized_pnl=0.3,
            )
        )
        session.add(
            WorkerOrder(
                worker_id=1,
                client_order_id="o1",
                symbol="BTCUSDT",
                side="buy",
                order_type="limit",
                status="NEW",
                quantity=0.5,
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
                margin_used="10.5",
                status="OPEN",
            )
        )
        session.add(
            WorkerCapital(
                worker_id=1,
                initial_capital=100000.0,
                current_capital=100000.0,
            )
        )
        session.commit()

        trade = session.query(WorkerTrade).one()
        assert type(trade.quantity) is float
        assert repr(trade.quantity) == "0.12345678"  # str 写入保真 8 位小数
        assert repr(trade.notional) == "0.3"  # DECIMAL(30,8) scale 截读清掉二进制尾数
        assert type(trade.fee) is float
        order = session.query(WorkerOrder).one()
        assert type(order.quantity) is float
        pos = session.query(WorkerPosition).one()
        assert repr(pos.margin_used) == "10.5"
        # quantity×price 混算（to_dict unrealized_pnl_pct 同款）不再 TypeError
        assert pos.to_dict()["unrealized_pnl_pct"] == 0
        capital = session.query(WorkerCapital).one()
        assert capital.initial_capital == 100000.0 and isinstance(capital.available_capital, float)


def test_money_column_not_float_for_gateway() -> None:
    """门禁同款判定：数量/资金列 isinstance(col.type, Float) 为 False 且是 PriceAsFloat。"""
    for table_col in (
        WorkerTrade.__table__.c.quantity,
        WorkerTrade.__table__.c.notional,
        WorkerTrade.__table__.c.fee,
        WorkerTrade.__table__.c.realized_pnl,
        WorkerOrder.__table__.c.quantity,
        WorkerOrder.__table__.c.filled_quantity,
        WorkerPosition.__table__.c.quantity,
        WorkerPosition.__table__.c.unrealized_pnl,
        WorkerPosition.__table__.c.realized_pnl,
        WorkerPosition.__table__.c.margin_used,
        WorkerCapital.__table__.c.initial_capital,
        WorkerCapital.__table__.c.margin_used,
    ):
        assert not isinstance(table_col.type, sa.Float), table_col
        assert isinstance(table_col.type, PriceAsFloat), table_col
