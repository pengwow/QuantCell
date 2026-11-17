"""K线周期历史列名统一改名 interval 的幂等迁移测试（vocab P2-10）"""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from collector.db.migrations import rename_kline_interval_columns

FEATURES_DDL = """
CREATE TABLE features (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol VARCHAR NOT NULL, feature_name VARCHAR NOT NULL,
    freq VARCHAR(20) NOT NULL, value REAL, created_at DATETIME, updated_at DATETIME
)
"""

ALERT_RULES_DDL = """
CREATE TABLE indicator_alert_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    indicator_id INTEGER NOT NULL, period VARCHAR(20) NOT NULL,
    operator VARCHAR(10) NOT NULL, value REAL, enabled BOOLEAN
)
"""


def _columns(session, table) -> list[str]:
    return [row[1] for row in session.execute(text(f"PRAGMA table_info('{table}')"))]


def test_renames_legacy_columns_preserving_rows():
    engine = create_engine("sqlite:///:memory:")
    with Session(engine) as session:
        session.execute(text(FEATURES_DDL))
        session.execute(text(ALERT_RULES_DDL))
        session.execute(
            text("INSERT INTO features (symbol, feature_name, freq, value) VALUES ('BTCUSDT', 'rsi', '1h', 62.5)")
        )
        session.execute(
            text("INSERT INTO indicator_alert_rules (indicator_id, period, operator, value) VALUES (1, '15m', '>', 70)")
        )
        session.commit()
        assert "freq" in _columns(session, "features")
        assert "period" in _columns(session, "indicator_alert_rules")

        rename_kline_interval_columns(session, "sqlite")

        assert "interval" in _columns(session, "features")
        assert "freq" not in _columns(session, "features")
        assert "interval" in _columns(session, "indicator_alert_rules")
        assert "period" not in _columns(session, "indicator_alert_rules")
        # 存量数据保留
        assert session.execute(text("SELECT interval FROM features")).scalar() == "1h"
        assert session.execute(text("SELECT interval FROM indicator_alert_rules")).scalar() == "15m"

        # 幂等：再跑一次不报错
        rename_kline_interval_columns(session, "sqlite")


def test_skips_when_tables_absent_or_already_renamed():
    engine = create_engine("sqlite:///:memory:")
    with Session(engine) as session:
        # 空库（新库由 create_all 直建 interval）：不报错
        rename_kline_interval_columns(session, "sqlite")
        # 只建新结构 features 表（已含 interval 列）：跳过不报错
        session.execute(text(FEATURES_DDL.replace("freq VARCHAR(20) NOT NULL", "interval VARCHAR(20) NOT NULL")))
        session.commit()
        rename_kline_interval_columns(session, "sqlite")
