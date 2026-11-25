"""归档检索的 kline 分支（本地 parquet 浏览）回归。

守护三件事：
- `kind=kline` 不再被归档枚举判非法，标的/数据/摘要都从本地 parquet 出；
- 时间单位按值归一（现货微秒 / 合约毫秒），出参恒为毫秒（硬编单位会算出 1970）；
- 周期缺省取该标的第一个可用周期，显式传周期时以参数为准。
"""

import pandas as pd
import pytest

from collector.services import kline_browse_service
from quality.parquet_provider import ParquetDataProvider


def _write_kline(root, candle_type, interval, symbol, start_us, rows):
    path = root / "crypto" / candle_type / "klines" / interval / f"{symbol}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(
        {
            "timestamp": [start_us + i * 3_600_000_000 for i in range(rows)],
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 1.0,
        }
    )
    df.to_parquet(path, index=False)
    return path


@pytest.fixture()
def parquet_root(tmp_path, monkeypatch):
    # 2026-07-01 00:00 UTC，微秒
    start = 1_782_864_000_000_000
    _write_kline(tmp_path, "spot", "1h", "BTCUSDT", start, rows=4)
    _write_kline(tmp_path, "future", "15m", "BTCUSDT", start // 1000, rows=3)
    monkeypatch.setattr(
        kline_browse_service,
        "ParquetDataProvider",
        lambda: ParquetDataProvider(base_dir=tmp_path),
    )
    return tmp_path


def test_symbols_are_read_from_local_parquet(parquet_root):
    assert kline_browse_service.list_symbols("spot") == ["BTCUSDT"]
    assert kline_browse_service.list_symbols("um") == ["BTCUSDT"]  # um/cm 都读 future 目录
    assert kline_browse_service.list_symbols("spot", "15m") == []


def test_meta_converts_micro_and_milliseconds_to_dates(parquet_root):
    spot = kline_browse_service.get_meta("spot", "BTCUSDT", "1h")
    assert spot["earliest_date"] == "2026-07-01"
    assert spot["total_rows"] == 4

    future = kline_browse_service.get_meta("um", "BTCUSDT")
    assert future["earliest_date"] == "2026-07-01"  # 合约落盘是毫秒，同样不能算出 1970
    assert future["total_rows"] == 3


def test_query_data_pages_and_normalizes_timestamps(parquet_root):
    start = 1_782_864_000_000  # 毫秒
    end = start + 24 * 3_600_000
    result = kline_browse_service.query_data("spot", "BTCUSDT", start, end, limit=2, offset=0, interval="1h")
    assert result["total"] == 4
    assert result["truncated"] is True
    assert [row["timestamp"] for row in result["rows"]] == [start, start + 3_600_000]

    page2 = kline_browse_service.query_data("spot", "BTCUSDT", start, end, limit=2, offset=2, interval="1h")
    assert page2["truncated"] is False
    assert len(page2["rows"]) == 2

def test_delete_symbol_scoped_to_interval(parquet_root):
    # 再有第二个周期文件，验证「只删当前周期」不会连坐
    _write_kline(parquet_root, "spot", "15m", "BTCUSDT", 1_782_864_000_000_000, rows=2)
    assert kline_browse_service.delete_symbol("spot", "BTCUSDT", "1h")
    assert kline_browse_service.list_symbols("spot", "1h") == []
    assert kline_browse_service.list_symbols("spot", "15m") == ["BTCUSDT"]
    assert kline_browse_service.delete_symbol("spot", "BTCUSDT", "1h") is None  # 幂等
