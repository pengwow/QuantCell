"""K线三表 timestamp 列 String→BIGINT 门禁与重建迁移测试（P2-14 数值收口）。

timestamp 此前存纳秒字符串：区间过滤靠字典序比较碰巧可用，但与毫秒写入源
（ws 持久化）混存、任意 python 层比较都易错。P2-14 收口为 BigInteger 纳秒
整型，迁移 DROP+create（存量K线可重拉），照 OHLC/ volume 迁移同策略。
"""

from sqlalchemy import BigInteger, String, create_engine, inspect, text
from sqlalchemy.orm import Session

# worker/strategy 两个 mapper 模块先注册，避免全局 mapper configure 失败（同 test_export_data）
import strategy.models
import worker.models
from collector.db.database import Base, _import_all_models
from collector.db.migrations import update_kline_timestamp_to_bigint
from collector.db.models import CryptoSpotKline

KLINE_TABLES = ("crypto_spot_klines", "crypto_future_klines", "stock_klines")


def test_kline_timestamp_columns_are_bigint() -> None:
    """K线三表 timestamp 列必须存在且为 BigInteger（禁 String/普通 Integer 回退）。"""
    _import_all_models()
    for table_name in KLINE_TABLES:
        table = Base.metadata.tables.get(table_name)
        assert table is not None, f"K线表 {table_name} 未在 metadata 注册"
        col = table.columns.get("timestamp")
        assert col is not None, f"{table_name}.timestamp 缺失"
        assert isinstance(col.type, BigInteger), (
            f"{table_name}.timestamp 应为 BigInteger 纳秒整型，实际 {col.type!r}（String timestamp 是被禁止的历史形态）"
        )
        assert not isinstance(col.type, String)


# 旧表 DDL：timestamp 为 String 列的历史形态（OHLC 已是 DECIMAL 的现形态）
OLD_DDL = """
CREATE TABLE crypto_spot_klines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol VARCHAR NOT NULL,
    interval VARCHAR NOT NULL,
    timestamp VARCHAR NOT NULL,
    open DECIMAL(40, 8) NOT NULL,
    high DECIMAL(40, 8) NOT NULL,
    low DECIMAL(40, 8) NOT NULL,
    close DECIMAL(40, 8) NOT NULL,
    volume DECIMAL(40, 8) NOT NULL,
    unique_kline VARCHAR NOT NULL UNIQUE,
    data_source VARCHAR(50) NOT NULL,
    created_at DATETIME,
    updated_at DATETIME
)
"""


def _ts_type(session):
    cols = {c["name"]: c["type"] for c in inspect(session.get_bind()).get_columns("crypto_spot_klines")}
    return cols["timestamp"]


def test_rebuilds_string_timestamp_to_bigint():
    engine = create_engine("sqlite:///:memory:")
    with Session(engine) as session:
        session.execute(text(OLD_DDL))
        session.commit()
        assert not isinstance(_ts_type(session), BigInteger)

        update_kline_timestamp_to_bigint(session, "sqlite")

        # 表按当前 ORM 重建：timestamp 为整型列，可直接写 int
        assert isinstance(_ts_type(session), BigInteger)
        session.add(
            CryptoSpotKline(
                symbol="BTCUSDT",
                interval="1h",
                timestamp=1700000000000000000,
                open=1,
                high=1,
                low=1,
                close=1,
                volume=1,
                unique_kline="BTCUSDT_1h_1700000000000000000",
            )
        )
        session.commit()
        row = session.query(CryptoSpotKline).one()
        assert row.timestamp == 1700000000000000000


def test_idempotent_and_data_kept():
    engine = create_engine("sqlite:///:memory:")
    with Session(engine) as session:
        session.execute(text(OLD_DDL))
        session.commit()
        update_kline_timestamp_to_bigint(session, "sqlite")

        session.add(
            CryptoSpotKline(
                symbol="ETHUSDT",
                interval="1d",
                timestamp=1700006400000000000,
                open=1,
                high=1,
                low=1,
                close=1,
                volume=1,
                unique_kline="ETHUSDT_1d_1700006400000000000",
            )
        )
        session.commit()

        # 幂等：第二次跑不报错，已有数据保留
        update_kline_timestamp_to_bigint(session, "sqlite")

        assert session.query(CryptoSpotKline).count() == 1
        assert isinstance(_ts_type(session), BigInteger)


def test_skips_when_table_absent():
    # 空库（表不存在）应跳过——首次建库由 create_all 按新模型负责
    engine = create_engine("sqlite:///:memory:")
    with Session(engine) as session:
        update_kline_timestamp_to_bigint(session, "sqlite")
