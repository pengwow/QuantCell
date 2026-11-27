"""standalone_downloader 落库纳秒与 skip 检查口径自检

历史 bug1：_save_to_database 把 timestamp 写成 str(毫秒)，而 P2-14 起列为
BIGINT 纳秒整型 → DB 副本时间戳错配。
历史 bug2：_check_data_exists 用毫秒整型过滤纳秒列恒为 False → 已存在天数
重复下载；且检查目标应是回测实际读取的 source Parquet（否则 DB 有但
parquet 缺的日期永远 skip、数据永远进不了 parquet）。
"""

from datetime import datetime

import pandas as pd
import sqlalchemy
from sqlalchemy.orm import sessionmaker

import collector.db.database as db_module
import strategy.models  # 注册 strategies 表，workers.strategy_id 外键才能解析
from backtest.standalone_downloader import StandaloneDataDownloader
from collector.db.database import Base
from collector.db.models import CryptoSpotKline

SIMPLE_TS_COL = 96  # 15m * 96 = 一整天


def _day_ns(date: str) -> list[int]:
    day = datetime.strptime(date, "%Y-%m-%d")
    return [int((day + pd.Timedelta(minutes=15) * i).timestamp() * 1_000_000_000) for i in range(SIMPLE_TS_COL)]


def test_save_to_database_writes_nanoseconds(tmp_path, monkeypatch):
    engine = sqlalchemy.create_engine(f"sqlite:///{tmp_path}/t.db")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(db_module, "init_database_config", lambda: None)
    monkeypatch.setattr(db_module, "engine", engine, raising=False)
    monkeypatch.setattr(db_module, "SessionLocal", sessionmaker(bind=engine), raising=False)

    downloader = StandaloneDataDownloader()
    open_ms = int(datetime(2026, 5, 1, 0, 0).timestamp() * 1000)
    df = pd.DataFrame(
        {
            "open_time": [open_ms],
            "open": 1.0,
            "high": 2.0,
            "low": 0.5,
            "close": 1.5,
            "volume": 10.0,
        }
    )

    assert downloader._save_to_database(df, "ETHUSDT", "15m", "spot") is True

    with sessionmaker(bind=engine)() as db:
        row = db.query(CryptoSpotKline).filter_by(symbol="ETHUSDT", interval="15m").one()
        assert row.timestamp == open_ms * 1_000_000


def test_check_data_exists_reads_source_parquet(tmp_path, monkeypatch):
    monkeypatch.setattr("utils.data_utils.get_source_data_dir", lambda: tmp_path)
    downloader = StandaloneDataDownloader()

    assert downloader._check_data_exists("ETHUSDT", "15m", "2026-05-01", "spot") is False

    file_path = tmp_path / "crypto" / "spot" / "klines" / "15m" / "ETHUSDT.parquet"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"timestamp": _day_ns("2026-05-01")}).to_parquet(file_path, index=False)

    assert downloader._check_data_exists("ETHUSDT", "15m", "2026-05-01", "spot") is True
    assert downloader._check_data_exists("ETHUSDT", "15m", "2026-05-02", "spot") is False


def test_check_data_exists_um_maps_to_future(tmp_path, monkeypatch):
    monkeypatch.setattr("utils.data_utils.get_source_data_dir", lambda: tmp_path)
    downloader = StandaloneDataDownloader()

    file_path = tmp_path / "crypto" / "future" / "klines" / "15m" / "ETHUSDT.parquet"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"timestamp": _day_ns("2026-05-01")}).to_parquet(file_path, index=False)

    assert downloader._check_data_exists("ETHUSDT", "15m", "2026-05-01", "um") is True
