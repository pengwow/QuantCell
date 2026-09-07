"""collector.services.deriv_service 单元测试。

覆盖衍生数据浏览服务：
- _validate / _symbol_dir 纯函数
- list_symbols: 目录扫描与 parquet 过滤
- get_meta: 文件名日期推断、纳秒/毫秒时间戳换算、损坏文件容错
- query_data: 纳秒/毫秒/秒三种时间戳单位分支、时间范围过滤、排序、分页与 truncated
- delete_data: 目录删除与不存在返回 None
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from collector.services.deriv_service import (
    VALID_DERIV_KINDS,
    VALID_MARKETS,
    DerivService,
    _symbol_dir,
    _validate,
)

NS_TS = 1_700_000_000_000_000_000  # 纳秒
MS_TS = 1_700_000_000_000  # 毫秒
SEC_TS = 1_700_000_000  # 秒


def _write_parquet(sym_dir: Path, filename: str, ts_list: list[int]) -> Path:
    """写入一个带 timestamp 列的 parquet 文件，用于元数据/查询测试。"""
    sym_dir.mkdir(parents=True, exist_ok=True)
    path = sym_dir / filename
    pd.DataFrame({"timestamp": ts_list}).to_parquet(path, index=False)
    return path


def _write_broken_parquet(sym_dir: Path, filename: str) -> Path:
    """写入一个无法被 pandas 解析的伪 parquet 文件。"""
    sym_dir.mkdir(parents=True, exist_ok=True)
    path = sym_dir / filename
    path.write_text("this is not a parquet file")
    return path


# =================== 纯函数 ===================


@pytest.mark.parametrize("kind", ["fundingRate", "openInterest"])
def test_validate_accepts_valid_kind(kind):
    _validate(kind, "um")


@pytest.mark.parametrize("market", ["spot", "um", "cm"])
def test_validate_accepts_valid_market(market):
    _validate("fundingRate", market)


@pytest.mark.parametrize("kind", ["", "foo", "kline", "unknown"])
def test_validate_rejects_invalid_kind(kind):
    with pytest.raises(ValueError, match="非法 deriv kind"):
        _validate(kind, "um")


@pytest.mark.parametrize("market", ["", "usdt", "Futures", "123"])
def test_validate_rejects_invalid_market(market):
    with pytest.raises(ValueError, match="非法 market"):
        _validate("fundingRate", market)


def test_symbol_dir_concatenates_kind_market_symbol():
    assert _symbol_dir(Path("/base"), "fundingRate", "um", "BTCUSDT") == Path("/base/fundingRate/um/BTCUSDT")


# =================== list_symbols ===================


def test_list_symbols_missing_market_dir_returns_empty(tmp_path):
    svc = DerivService(tmp_path)
    assert svc.list_symbols("fundingRate", "um") == []


def test_list_symbols_returns_sorted_symbols_with_parquet(tmp_path):
    _write_parquet(tmp_path / "fundingRate" / "um" / "BTCUSDT", "2024-01-01.parquet", [MS_TS])
    _write_parquet(tmp_path / "fundingRate" / "um" / "ETHUSDT", "2024-01-01.parquet", [MS_TS])
    # 无 parquet 的目录不应出现在结果中
    (tmp_path / "fundingRate" / "um" / "SOLUSDT").mkdir(parents=True)

    svc = DerivService(tmp_path)
    assert svc.list_symbols("fundingRate", "um") == ["BTCUSDT", "ETHUSDT"]


def test_list_symbols_ignores_files_and_kind_mismatch(tmp_path):
    _write_parquet(tmp_path / "fundingRate" / "um" / "BTCUSDT", "2024-01-01.parquet", [MS_TS])
    _write_parquet(tmp_path / "openInterest" / "um" / "ETHUSDT", "2024-01-01.parquet", [MS_TS])

    svc = DerivService(tmp_path)
    assert svc.list_symbols("fundingRate", "um") == ["BTCUSDT"]


# =================== get_meta ===================


def test_get_meta_missing_symbol_dir_returns_none(tmp_path):
    svc = DerivService(tmp_path)
    assert svc.get_meta("fundingRate", "um", "BTCUSDT") is None


def test_get_meta_symbol_dir_without_parquet_returns_none(tmp_path):
    (tmp_path / "fundingRate" / "um" / "BTCUSDT").mkdir(parents=True)
    svc = DerivService(tmp_path)
    assert svc.get_meta("fundingRate", "um", "BTCUSDT") is None


def test_get_meta_infers_dates_and_row_count(tmp_path):
    sym_dir = tmp_path / "fundingRate" / "um" / "BTCUSDT"
    _write_parquet(sym_dir, "BTCUSDT_2024-01-15.parquet", [MS_TS, MS_TS + 60_000])
    _write_parquet(sym_dir, "BTCUSDT_20240116.parquet", [MS_TS + 120_000])

    svc = DerivService(tmp_path)
    meta = svc.get_meta("fundingRate", "um", "BTCUSDT")

    assert meta is not None
    assert meta["symbol"] == "BTCUSDT"
    assert meta["kind"] == "fundingRate"
    assert meta["market"] == "um"
    # 文件名推断日期（支持横线格式与紧凑格式）
    assert meta["earliest_date"] == "2024-01-15"
    assert meta["latest_date"] == "2024-01-16"
    assert meta["total_rows"] == 3
    assert meta["file_count"] == 2


def test_get_meta_handles_nanosecond_timestamps(tmp_path):
    sym_dir = tmp_path / "openInterest" / "um" / "BTCUSDT"
    _write_parquet(sym_dir, "2024-01-01.parquet", [NS_TS, NS_TS + 1_000_000])  # 间隔 1ms

    svc = DerivService(tmp_path)
    meta = svc.get_meta("openInterest", "um", "BTCUSDT")

    # 纳秒时间戳应被换算为毫秒
    assert meta["_earliest_ts_ms"] == NS_TS // 1_000_000
    assert meta["_latest_ts_ms"] == (NS_TS + 1_000_000) // 1_000_000


def test_get_meta_keeps_millisecond_timestamps(tmp_path):
    sym_dir = tmp_path / "fundingRate" / "um" / "BTCUSDT"
    _write_parquet(sym_dir, "2024-01-01.parquet", [MS_TS, MS_TS + 60_000])

    svc = DerivService(tmp_path)
    meta = svc.get_meta("fundingRate", "um", "BTCUSDT")

    assert meta["_earliest_ts_ms"] == MS_TS
    assert meta["_latest_ts_ms"] == MS_TS + 60_000


def test_get_meta_skips_corrupt_parquet(tmp_path):
    sym_dir = tmp_path / "fundingRate" / "um" / "BTCUSDT"
    _write_parquet(sym_dir, "2024-01-01.parquet", [MS_TS])
    _write_broken_parquet(sym_dir, "broken.parquet")

    meta = DerivService(tmp_path).get_meta("fundingRate", "um", "BTCUSDT")

    assert meta is not None
    assert meta["total_rows"] == 1
    assert meta["file_count"] == 2


def test_get_meta_empty_parquet_does_not_break_row_count(tmp_path):
    sym_dir = tmp_path / "fundingRate" / "um" / "BTCUSDT"
    (sym_dir).mkdir(parents=True)
    pd.DataFrame(columns=["timestamp"]).to_parquet(sym_dir / "empty.parquet", index=False)

    meta = DerivService(tmp_path).get_meta("fundingRate", "um", "BTCUSDT")

    assert meta["total_rows"] == 0
    assert meta["file_count"] == 1


# =================== query_data ===================


def test_query_data_missing_dir_returns_empty(tmp_path):
    result = DerivService(tmp_path).query_data("fundingRate", "um", "BTCUSDT", 0, 0)
    assert result == {"total": 0, "rows": [], "truncated": False}


def test_query_data_no_parquet_returns_empty(tmp_path):
    (tmp_path / "fundingRate" / "um" / "BTCUSDT").mkdir(parents=True)
    result = DerivService(tmp_path).query_data("fundingRate", "um", "BTCUSDT", 0, 0)
    assert result == {"total": 0, "rows": [], "truncated": False}


def test_query_data_filters_sort_and_paginates(tmp_path):
    sym_dir = tmp_path / "fundingRate" / "um" / "BTCUSDT"
    _write_parquet(sym_dir, "2024-01-01.parquet", [MS_TS + 2000, MS_TS + 5000])
    _write_parquet(sym_dir, "2024-01-02.parquet", [MS_TS + 1000, MS_TS + 4000])

    result = DerivService(tmp_path).query_data(
        "fundingRate", "um", "BTCUSDT", start_time=MS_TS + 2000, end_time=MS_TS + 4000, limit=10
    )

    # 跨文件合并后按时间升序，范围过滤取 [2000, 4000]
    assert result["total"] == 2
    assert [row["timestamp"] for row in result["rows"]] == [MS_TS + 2000, MS_TS + 4000]
    assert result["truncated"] is False


def test_query_data_marks_truncated_when_page_overflows(tmp_path):
    sym_dir = tmp_path / "fundingRate" / "um" / "BTCUSDT"
    _write_parquet(sym_dir, "2024-01-01.parquet", [MS_TS + i * 1000 for i in range(6)])

    result = DerivService(tmp_path).query_data(
        "fundingRate", "um", "BTCUSDT", start_time=0, end_time=MS_TS + 999_999, limit=2, offset=1
    )

    assert result["total"] == 6
    # 6 > 2 + 1 说明还有剩余页
    assert result["truncated"] is True
    assert len(result["rows"]) == 2
    assert result["rows"][0]["timestamp"] == MS_TS + 1000


def test_query_data_nanosecond_branch(tmp_path):
    sym_dir = tmp_path / "fundingRate" / "um" / "BTCUSDT"
    _write_parquet(sym_dir, "2024-01-01.parquet", [NS_TS, NS_TS + 60_000_000_000])  # 间隔 60s

    result = DerivService(tmp_path).query_data(
        "fundingRate", "um", "BTCUSDT", start_time=NS_TS // 1_000_000, end_time=NS_TS // 1_000_000 + 1000
    )

    assert result["total"] == 1
    assert result["rows"][0]["timestamp"] == NS_TS


def test_query_data_second_branch(tmp_path):
    sym_dir = tmp_path / "fundingRate" / "um" / "BTCUSDT"
    _write_parquet(sym_dir, "2024-01-01.parquet", [SEC_TS, SEC_TS + 60])

    result = DerivService(tmp_path).query_data(
        "fundingRate", "um", "BTCUSDT", start_time=SEC_TS * 1000, end_time=(SEC_TS + 1) * 1000
    )

    assert result["total"] == 1
    assert result["rows"][0]["timestamp"] == SEC_TS


def test_query_data_skips_corrupt_parquet(tmp_path):
    sym_dir = tmp_path / "fundingRate" / "um" / "BTCUSDT"
    _write_parquet(sym_dir, "2024-01-01.parquet", [MS_TS])
    _write_broken_parquet(sym_dir, "broken.parquet")

    result = DerivService(tmp_path).query_data("fundingRate", "um", "BTCUSDT", 0, MS_TS + 100)

    assert result["total"] == 1


def test_query_data_converts_nan_to_none(tmp_path):
    sym_dir = tmp_path / "fundingRate" / "um" / "BTCUSDT"
    sym_dir.mkdir(parents=True)
    pd.DataFrame({"timestamp": [MS_TS], "value": [float("nan")]}).to_parquet(
        sym_dir / "2024-01-01.parquet", index=False
    )

    result = DerivService(tmp_path).query_data("fundingRate", "um", "BTCUSDT", 0, MS_TS + 100)

    assert result["total"] == 1
    assert result["rows"][0]["value"] is None


# =================== delete_data ===================


def test_delete_data_removes_symbol_dir(tmp_path):
    sym_dir = tmp_path / "fundingRate" / "um" / "BTCUSDT"
    _write_parquet(sym_dir, "2024-01-01.parquet", [MS_TS])

    svc = DerivService(tmp_path)
    deleted = svc.delete_data("fundingRate", "um", "BTCUSDT")

    assert deleted == sym_dir
    assert not sym_dir.exists()
    assert (tmp_path / "fundingRate" / "um").exists()


def test_query_data_delete_missing_dir_returns_none(tmp_path):
    svc = DerivService(tmp_path)
    assert svc.delete_data("fundingRate", "um", "BTCUSDT") is None
