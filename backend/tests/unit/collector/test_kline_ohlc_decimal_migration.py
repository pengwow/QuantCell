"""K线三表 OHLC 四列 String→DECIMAL 重建迁移测试（P2-11 价格域收口）"""

from decimal import Decimal

from sqlalchemy import Numeric, create_engine, inspect, text
from sqlalchemy.orm import Session

# worker/strategy 两个 mapper 模块先注册，避免全局 mapper configure 失败（同 test_export_data）
import strategy.models
import worker.models
from collector.db.migrations import update_kline_ohlc_to_decimal

# 旧表 DDL：OHLC 为 String 列的历史形态（volume 已是 DECIMAL 的中间态）
OLD_DDL = """
CREATE TABLE crypto_spot_klines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol VARCHAR NOT NULL,
    interval VARCHAR NOT NULL,
    timestamp VARCHAR NOT NULL,
    open VARCHAR NOT NULL,
    high VARCHAR NOT NULL,
    low VARCHAR NOT NULL,
    close VARCHAR NOT NULL,
    volume DECIMAL(40, 8) NOT NULL,
    unique_kline VARCHAR NOT NULL UNIQUE,
    data_source VARCHAR(50) NOT NULL,
    created_at DATETIME,
    updated_at DATETIME
)
"""


def _ohlc_types(session):
    cols = {c["name"]: c["type"] for c in inspect(session.get_bind()).get_columns("crypto_spot_klines")}
    return [cols[c] for c in ("open", "high", "low", "close")]


def test_rebuilds_string_ohlc_to_decimal():
    engine = create_engine("sqlite:///:memory:")
    with Session(engine) as session:
        session.execute(text(OLD_DDL))
        session.commit()
        assert not any(isinstance(t, Numeric) for t in _ohlc_types(session))

        update_kline_ohlc_to_decimal(session, "sqlite")

        # 表按当前 ORM 重建：OHLC 四列全部 DECIMAL，可正常读写 Decimal
        assert all(isinstance(t, Numeric) for t in _ohlc_types(session))
        from collector.db.models import CryptoSpotKline

        session.add(
            CryptoSpotKline(
                symbol="BTCUSDT",
                interval="1h",
                timestamp="1700000000000000000",
                open=Decimal("43250.10"),
                high=Decimal("43300.00"),
                low=Decimal("43100.55"),
                close=Decimal("43280.77"),
                volume=Decimal("12.5"),
                unique_kline="BTCUSDT_1h_1700000000000000000",
            )
        )
        session.commit()
        row = session.query(CryptoSpotKline).one()
        assert row.close == Decimal("43280.77")
        assert float(row.close) == 43280.77

    # 三表统一：stock 表同样被重建
    engine2 = create_engine("sqlite:///:memory:")
    with Session(engine2) as session2:
        session2.execute(text(OLD_DDL.replace("crypto_spot_klines", "stock_klines")))
        session2.commit()
        update_kline_ohlc_to_decimal(session2, "sqlite")
        cols = {c["name"]: c["type"] for c in inspect(session2.get_bind()).get_columns("stock_klines")}
        assert isinstance(cols["open"], Numeric)


def test_idempotent_and_data_kept():
    engine = create_engine("sqlite:///:memory:")
    with Session(engine) as session:
        session.execute(text(OLD_DDL))
        session.commit()
        update_kline_ohlc_to_decimal(session, "sqlite")

        from collector.db.models import CryptoSpotKline

        session.add(
            CryptoSpotKline(
                symbol="ETHUSDT",
                interval="1d",
                timestamp="1700006400000000000",
                open=Decimal(2200),
                high=Decimal(2250),
                low=Decimal(2190),
                close=Decimal("2240.5"),
                volume=Decimal(3),
                unique_kline="ETHUSDT_1d_1700006400000000000",
            )
        )
        session.commit()

        # 幂等：第二次跑不报错，已有数据保留
        update_kline_ohlc_to_decimal(session, "sqlite")

        assert session.query(CryptoSpotKline).count() == 1
        assert all(isinstance(t, Numeric) for t in _ohlc_types(session))


def test_skips_when_table_absent():
    # 空库（表不存在）应跳过——首次建库由 create_all 按新模型负责
    engine = create_engine("sqlite:///:memory:")
    with Session(engine) as session:
        update_kline_ohlc_to_decimal(session, "sqlite")
