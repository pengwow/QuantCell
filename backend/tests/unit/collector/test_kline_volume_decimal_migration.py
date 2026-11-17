"""K线三表 volume 列 String→DECIMAL 重建迁移测试（P2-4 B-11）"""

from decimal import Decimal

from sqlalchemy import Numeric, create_engine, inspect, text
from sqlalchemy.orm import Session

# worker/strategy 两个 mapper 模块先注册，避免全局 mapper configure 失败（同 test_export_data）
import strategy.models
import worker.models
from collector.db.migrations import update_kline_volume_to_decimal

# 旧表 DDL：volume 为 String 列的历史形态（迁移仅 DROP 重建，无需逐列精确）
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
    volume VARCHAR NOT NULL,
    unique_kline VARCHAR NOT NULL UNIQUE,
    data_source VARCHAR(50) NOT NULL,
    created_at DATETIME,
    updated_at DATETIME
)
"""


def _volume_type(session):
    cols = {c["name"]: c["type"] for c in inspect(session.get_bind()).get_columns("crypto_spot_klines")}
    return cols["volume"]


def test_rebuilds_string_volume_to_decimal():
    engine = create_engine("sqlite:///:memory:")
    with Session(engine) as session:
        session.execute(text(OLD_DDL))
        session.commit()
        assert not isinstance(_volume_type(session), Numeric)

        update_kline_volume_to_decimal(session, "sqlite")

        # 表按当前 ORM 重建：volume 是 DECIMAL，可正常读写 Decimal
        assert isinstance(_volume_type(session), Numeric)
        from collector.db.models import CryptoSpotKline

        session.add(
            CryptoSpotKline(
                symbol="BTCUSDT",
                interval="1h",
                timestamp="1700000000000000000",
                open="1",
                high="1",
                low="1",
                close="1",
                volume=Decimal("12.5"),
                unique_kline="BTCUSDT_1h_1700000000000000000",
            )
        )
        session.commit()
        row = session.query(CryptoSpotKline).one()
        assert isinstance(row.volume, Decimal)
        assert row.volume == Decimal("12.5")


def test_idempotent_and_data_kept():
    engine = create_engine("sqlite:///:memory:")
    with Session(engine) as session:
        session.execute(text(OLD_DDL))
        session.commit()
        update_kline_volume_to_decimal(session, "sqlite")

        from collector.db.models import CryptoSpotKline

        session.add(
            CryptoSpotKline(
                symbol="ETHUSDT",
                interval="1d",
                timestamp="1700006400000000000",
                open="1",
                high="1",
                low="1",
                close="1",
                volume=Decimal(3),
                unique_kline="ETHUSDT_1d_1700006400000000000",
            )
        )
        session.commit()

        # 幂等：第二次跑不报错，已有数据保留
        update_kline_volume_to_decimal(session, "sqlite")

        assert session.query(CryptoSpotKline).count() == 1
        assert isinstance(_volume_type(session), Numeric)


def test_skips_when_table_absent():
    # 空库（表不存在）应跳过——首次建库由 create_all 按新模型负责
    engine = create_engine("sqlite:///:memory:")
    with Session(engine) as session:
        update_kline_volume_to_decimal(session, "sqlite")
