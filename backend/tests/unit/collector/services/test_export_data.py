"""ExportData 导出功能最小测试"""

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Worker.relationship("Strategy") 是字符串引用，两个 mapper 模块都注册后 configure 才能通过
import strategy.models
import worker.models
from collector.db.models import Base, CryptoSpotKline
from collector.services.data_service import ExportData


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[CryptoSpotKline.__table__])
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _add_kline(session, symbol, ts_ms):
    session.add(
        CryptoSpotKline(
            symbol=symbol,
            interval="1d",
            timestamp=str(ts_ms),
            open="100",
            high="110",
            low="90",
            close="105",
            volume="10",
            unique_kline=f"{symbol}-1d-{ts_ms}",
        )
    )
    session.commit()


def test_export_success_filters_and_writes_csv(db_session, tmp_path):
    # 时间戳对应 UTC：11-14T22:13（界外）、11-15T00:00（日线开盘）、11-15T22:13（界内）
    _add_kline(db_session, "BTCUSDT", 1700000000000)
    _add_kline(db_session, "BTCUSDT", 1700006400000)
    _add_kline(db_session, "BTCUSDT", 1700086400000)

    exporter = ExportData(db=db_session)
    result = exporter.export_kline_data(
        ["BTCUSDT"],
        interval="1d",
        start="2023-11-15",
        end="2023-11-16",
        candle_type="spot",
        save_dir=str(tmp_path),
    )

    assert result["success"] is True
    assert len(result["exported_files"]) == 1
    df = pd.read_csv(result["exported_files"][0], dtype={"timestamp": str})
    # 11-14 的记录被 start 过滤，11-15 两条保留，且按时间升序
    assert len(df) == 2
    assert list(df["timestamp"]) == ["1700006400000", "1700086400000"]


def test_export_missing_symbol_records_gap(db_session, tmp_path):
    exporter = ExportData(db=db_session)
    result = exporter.export_kline_data(["ETHUSDT"], interval="1d", candle_type="spot", save_dir=str(tmp_path))

    assert result["success"] is True
    assert result["exported_files"] == []
    assert "ETHUSDT" in result["missing_ranges"]


def test_export_invalid_candle_type(db_session, tmp_path):
    exporter = ExportData(db=db_session)
    with pytest.raises(ValueError):
        exporter.export_kline_data(["BTCUSDT"], candle_type="unknown", save_dir=str(tmp_path))
