"""ArchiveService 业务编排层单元测试。

覆盖:
- create_download_task: 委托 task_manager, 7 个 kind → 7 个 task_type 映射, K 线类需要 interval
- query_data: 委托 factory + read_range
- get_meta: 委托 read_meta
- list_symbols: 扫描目录
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from collector.services.archive_service import (
    KIND_TASK_TYPE,
    ArchiveService,
)
from exchange.binance.archive.kinds import ArchiveKind, MarketType

# =================== create_download_task ===================


def test_create_download_task_uses_task_manager():
    """create_download_task 必须通过 task_manager.create_task 创建任务。"""
    svc = ArchiveService(base_dir="/tmp", proxy="http://proxy:8080")
    with patch("collector.services.archive_service.task_manager") as mock_tm:
        mock_tm.create_task.return_value = "task-123"
        task_id = svc.create_download_task(
            symbols=["BTCUSDT"],
            kind=ArchiveKind.AGG_TRADES,
            market=MarketType.SPOT,
            start_date="2024-12-01",
            end_date="2024-12-02",
            mode="inc",
        )
    assert task_id == "task-123"
    mock_tm.create_task.assert_called_once()
    kwargs = mock_tm.create_task.call_args.kwargs
    assert kwargs["task_type"] == "archive_agg_trades"
    assert kwargs["params"]["symbols"] == ["BTCUSDT"]
    assert kwargs["params"]["market"] == "spot"
    assert kwargs["params"]["start_date"] == "2024-12-01"
    assert kwargs["params"]["end_date"] == "2024-12-02"
    assert kwargs["params"]["mode"] == "inc"


def test_create_download_task_dispatches_correct_kind():
    """K 线类需要透传 interval, 并映射到 archive_mark_klines 任务类型。"""
    svc = ArchiveService(base_dir="/tmp")
    with patch("collector.services.archive_service.task_manager") as mock_tm:
        svc.create_download_task(
            symbols=["BTCUSDT"],
            kind=ArchiveKind.MARK_KLINES,
            market=MarketType.FUTURES_UM,
            start_date="2024-12-01",
            end_date="2024-12-02",
            mode="inc",
            interval="1h",
        )
    kwargs = mock_tm.create_task.call_args.kwargs
    assert kwargs["task_type"] == "archive_mark_klines"
    assert kwargs["params"]["interval"] == "1h"


@pytest.mark.parametrize(
    "kind, expected_task_type",
    [
        (ArchiveKind.AGG_TRADES, "archive_agg_trades"),
        (ArchiveKind.TRADES, "archive_trades"),
        (ArchiveKind.BOOK_DEPTH, "archive_book_depth"),
        (ArchiveKind.BOOK_TICKER, "archive_book_ticker"),
        (ArchiveKind.MARK_KLINES, "archive_mark_klines"),
        (ArchiveKind.INDEX_KLINES, "archive_index_klines"),
        (ArchiveKind.PREMIUM_KLINES, "archive_premium_klines"),
    ],
)
def test_create_download_task_kind_to_task_type_mapping(kind, expected_task_type):
    """7 个 kind → 7 个 task_type 枚举一一对应。"""
    svc = ArchiveService(base_dir="/tmp")
    # K 线类必须传 interval
    kwargs = (
        {"interval": "1h"}
        if kind
        in (
            ArchiveKind.MARK_KLINES,
            ArchiveKind.INDEX_KLINES,
            ArchiveKind.PREMIUM_KLINES,
        )
        else {}
    )
    with patch("collector.services.archive_service.task_manager") as mock_tm:
        svc.create_download_task(
            symbols=["BTCUSDT"],
            kind=kind,
            market=MarketType.SPOT,
            start_date="2024-12-01",
            end_date="2024-12-02",
            **kwargs,
        )
    call_kwargs = mock_tm.create_task.call_args.kwargs
    assert call_kwargs["task_type"] == expected_task_type
    # 7 项全在映射表里
    assert KIND_TASK_TYPE[kind] == expected_task_type


def test_create_download_task_kline_without_interval_raises():
    """K 线类缺 interval 必须抛 ValueError。"""
    svc = ArchiveService(base_dir="/tmp")
    with pytest.raises(ValueError, match="requires interval"):
        svc.create_download_task(
            symbols=["BTCUSDT"],
            kind=ArchiveKind.MARK_KLINES,
            market=MarketType.SPOT,
            start_date="2024-12-01",
            end_date="2024-12-02",
        )


def test_create_download_task_kline_invalid_interval_raises():
    """K 线类给非法 interval 必须抛 ValueError。"""
    svc = ArchiveService(base_dir="/tmp")
    with pytest.raises(ValueError, match="requires interval"):
        svc.create_download_task(
            symbols=["BTCUSDT"],
            kind=ArchiveKind.MARK_KLINES,
            market=MarketType.SPOT,
            start_date="2024-12-01",
            end_date="2024-12-02",
            interval="4h",  # 不在允许的 8 个之内
        )


def test_create_download_task_non_kline_accepts_no_interval():
    """非 K 线类 (aggTrades) 不需要 interval。"""
    svc = ArchiveService(base_dir="/tmp")
    with patch("collector.services.archive_service.task_manager") as mock_tm:
        task_id = svc.create_download_task(
            symbols=["BTCUSDT"],
            kind=ArchiveKind.AGG_TRADES,
            market=MarketType.SPOT,
            start_date="2024-12-01",
            end_date="2024-12-02",
        )
    assert task_id is not None
    kwargs = mock_tm.create_task.call_args.kwargs
    assert kwargs["params"]["interval"] is None


# =================== get_meta ===================


def test_get_meta_returns_dict():
    """get_meta 直接委托 read_meta, 返回 dict 透传。"""
    svc = ArchiveService(base_dir="/tmp")
    with patch("collector.services.archive_service.read_meta") as mock_read:
        mock_read.return_value = {"symbol": "BTCUSDT", "kind": "aggTrades"}
        meta = svc.get_meta(ArchiveKind.AGG_TRADES, MarketType.SPOT, "BTCUSDT")
    assert meta == {"symbol": "BTCUSDT", "kind": "aggTrades"}


def test_get_meta_returns_none_when_missing():
    """_meta.json 不存在时 get_meta 返回 None。"""
    svc = ArchiveService(base_dir="/tmp")
    with patch("collector.services.archive_service.read_meta") as mock_read:
        mock_read.return_value = None
        meta = svc.get_meta(ArchiveKind.AGG_TRADES, MarketType.SPOT, "BTCUSDT")
    assert meta is None


# =================== list_symbols ===================


def test_list_symbols_returns_sorted_subdirs_with_parquet(tmp_path: Path):
    """list_symbols 只返回含 parquet 的目录, 按字典序排序。"""
    base = tmp_path
    spot = base / "spot" / "aggTrades"
    spot.mkdir(parents=True)
    for sym in ("BTCUSDT", "ETHUSDT", "ADAUSDT"):
        sym_dir = spot / sym
        sym_dir.mkdir()
        (sym_dir / f"{sym}-aggTrades-2024-12-01.parquet").touch()
    # 放个文件, 不应被识别为 symbol
    (spot / "readme.txt").write_text("not a dir")

    svc = ArchiveService(base_dir=base)
    result = svc.list_symbols(ArchiveKind.AGG_TRADES, MarketType.SPOT)
    assert result == ["ADAUSDT", "BTCUSDT", "ETHUSDT"]


def test_list_symbols_filters_meta_only_shell_dirs(tmp_path: Path):
    """只有 _meta.json 没有 parquet 的空壳目录必须被过滤（历史上下载失败留下的
    meta 空壳会让归档树显示大量点开为空的 symbol, 用户看到的"都是 0"一半源于此）。
    """
    spot = tmp_path / "spot" / "aggTrades"
    shell = spot / "BNBUSDT"  # 空壳: 只有 _meta.json
    shell.mkdir(parents=True)
    (shell / "_meta.json").write_text("{}", encoding="utf-8")
    real = spot / "BTCUSDT"
    real.mkdir(parents=True)
    (real / "BTCUSDT-aggTrades-2024-12-01.parquet").touch()

    svc = ArchiveService(base_dir=tmp_path)
    result = svc.list_symbols(ArchiveKind.AGG_TRADES, MarketType.SPOT)
    assert result == ["BTCUSDT"]


def test_list_symbols_empty_when_dir_missing(tmp_path: Path):
    """目录不存在返回空列表, 不抛异常。"""
    svc = ArchiveService(base_dir=tmp_path)
    result = svc.list_symbols(ArchiveKind.AGG_TRADES, MarketType.SPOT)
    assert result == []


# =================== query_data ===================


def test_query_data_delegates_to_factory(tmp_path: Path):
    """query_data 必须通过 factory.create + read_range。"""
    svc = ArchiveService(base_dir=tmp_path, proxy="http://proxy:8080")
    fake_fetcher = MagicMock()
    fake_fetcher.read_range.return_value = {"total": 5, "rows": [], "truncated": False}
    with patch("collector.services.archive_service.BinanceArchiveFactory.create") as mock_create:
        mock_create.return_value = fake_fetcher
        result = svc.query_data(
            ArchiveKind.AGG_TRADES,
            MarketType.SPOT,
            "BTCUSDT",
            start_time=0,
            end_time=9_999_999_999_999,
            limit=10,
            offset=0,
        )
    mock_create.assert_called_once()
    call_kwargs = mock_create.call_args.kwargs
    assert call_kwargs["base_dir"] == str(tmp_path)
    assert call_kwargs["symbol"] == "BTCUSDT"
    assert call_kwargs["proxy"] == "http://proxy:8080"
    fake_fetcher.read_range.assert_called_once_with("BTCUSDT", 0, 9_999_999_999_999, 10, 0)
    assert result == {"total": 5, "rows": [], "truncated": False}


# =================== get_watermark ===================


def _write_meta(save_dir: Path, **overrides) -> None:
    """造一份 `_meta.json`（字段取值按 archive_meta spec，可覆盖）。"""
    import json

    save_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "symbol": save_dir.name,
        "kind": save_dir.parent.name,
        "market": save_dir.parent.parent.name,
        "earliest_date": "2024-01-01",
        "latest_date": "2024-01-02",
        "total_rows": 100,
        "file_count": 1,
        "corrupt_dates": [],
        "updated_at": "2024-01-02T08:00:00.000000000+08:00",
    }
    meta.update(overrides)
    (save_dir / "_meta.json").write_text(json.dumps(meta), encoding="utf-8")


def test_get_watermark_aggregates_per_kind(tmp_path: Path):
    """按 kind 求和 total_rows、计数 symbol、取 min/max 日期；storage 按 kind 累加 parquet 体积。"""
    base = tmp_path / "archive"
    agg_btc = base / "spot" / "aggTrades" / "BTCUSDT"
    _write_meta(agg_btc, total_rows=1000, earliest_date="2024-01-01", latest_date="2024-03-05")
    (agg_btc / "BTCUSDT-aggTrades-2024-03-05.parquet").write_bytes(b"x" * 10)
    agg_eth = base / "spot" / "aggTrades" / "ETHUSDT"
    _write_meta(
        agg_eth,
        total_rows=250,
        earliest_date="2023-05-01",
        latest_date="2024-03-06",
        updated_at="2024-03-06T09:00:00.000000000+08:00",
    )
    (agg_eth / "ETHUSDT-aggTrades-2024-03-06.parquet").write_bytes(b"y" * 20)
    mark = base / "um" / "markPriceKlines" / "BTCUSDT"
    _write_meta(
        mark,
        kind="markPriceKlines",
        total_rows=480,
        earliest_date="2024-02-01",
        latest_date="2024-02-29",
    )
    (mark / "BTCUSDT-markPriceKlines-1h-2024-02-29.parquet").write_bytes(b"z" * 5)
    # 认不出 kind 的目录（既无 _meta.json、路径段也不含 kind）必须被忽略
    (base / "notes" / "readme.parquet").parent.mkdir(parents=True)
    (base / "notes" / "readme.parquet").write_bytes(b"q" * 999)

    result = ArchiveService(base_dir=base).get_watermark()

    by_kind = {w["kind"]: w for w in result["watermarks"]}
    assert sorted(by_kind) == ["aggTrades", "markPriceKlines"]
    assert by_kind["aggTrades"]["symbol_count"] == 2
    assert by_kind["aggTrades"]["total_rows"] == 1250
    assert by_kind["aggTrades"]["earliest_date"] == "2023-05-01"
    assert by_kind["aggTrades"]["latest_date"] == "2024-03-06"
    # updated_at 取 max（跨时区比较按时间戳，不按字符串）
    assert by_kind["aggTrades"]["updated_at"] == "2024-03-06T09:00:00.000000000+08:00"
    assert by_kind["markPriceKlines"]["symbol_count"] == 1
    assert by_kind["markPriceKlines"]["total_rows"] == 480

    storage = {s["kind"]: s["bytes"] for s in result["storage"]}
    assert storage == {"aggTrades": 30, "markPriceKlines": 5}
    assert result["total_bytes"] == 35


def test_get_watermark_returns_empty_arrays_when_no_data(tmp_path: Path):
    """空目录 → 空数组，不补 0 行占位。"""
    result = ArchiveService(base_dir=tmp_path).get_watermark()
    assert result == {"watermarks": [], "storage": [], "total_bytes": 0}


def test_get_watermark_corrupt_parquet_skips_watermark(tmp_path: Path):
    """读不了 footer 的 parquet（只有字节不是真 parquet）：进 storage 不进 watermarks。"""
    sym = tmp_path / "fundingRate" / "um" / "BTCUSDT"
    sym.mkdir(parents=True)
    (sym / "BTCUSDT-fundingRate-20261107.parquet").write_bytes(b"f" * 7)

    result = ArchiveService(base_dir=tmp_path).get_watermark()
    assert result["watermarks"] == []
    assert result["storage"] == [{"kind": "fundingRate", "bytes": 7}]
    assert result["total_bytes"] == 7


# =================== get_watermark: 数据池布局（无 _meta.json） ===================


def _write_parquet(path: Path, timestamps: list[int], rows: int | None = None) -> int:
    """真写一个 parquet（单时间列 + 占位列），返回写出的字节数。"""
    import pyarrow as pa
    import pyarrow.parquet as pq

    path.parent.mkdir(parents=True, exist_ok=True)
    count = len(timestamps) if rows is None else rows
    table = pa.table(
        {
            "timestamp": pa.array(timestamps, type=pa.int64()),
            "value": pa.array([float(i) for i in range(count)], type=pa.float64()),
        }
    )
    pq.write_table(table, path)
    return path.stat().st_size


def _write_pandas_index_parquet(path: Path, days: list[str]) -> int:
    """pandas 风格落盘：时间在索引列 `__index_level_0__`，没有 timestamp 列。"""
    import pandas as pd

    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(
        {"value": [float(i) for i in range(len(days))]},
        index=pd.to_datetime(days),
    )
    frame.to_parquet(path)
    return path.stat().st_size


def test_get_watermark_pool_kline_layout(tmp_path: Path):
    """数据池 K 线布局：同 symbol 多周期去重、行数累加、日期取全部文件 stats 的 min/max、
    体积累加。三个文件故意混用 微秒 / 毫秒 / pandas 索引列（无 timestamp 列）。
    """
    one_hour_us = [1735689600000000, 1735693200000000]  # 2025-01-01 00:00 / 01:00 UTC
    fifteen_min_ms = [1740787200000, 1740790800000, 1740794400000]  # 2025-03-01 00:00/01:00/02:00
    index_days = ["2026-11-18", "2026-11-19"]

    size_a = _write_parquet(tmp_path / "crypto" / "spot" / "klines" / "1h" / "BTCUSDT.parquet", one_hour_us)
    size_b = _write_parquet(tmp_path / "crypto" / "spot" / "klines" / "15m" / "BTCUSDT.parquet", fifteen_min_ms)
    size_c = _write_pandas_index_parquet(
        tmp_path / "crypto" / "future" / "klines" / "1h" / "ETHUSDT.parquet", index_days
    )

    result = ArchiveService(base_dir=tmp_path).get_watermark()

    by_kind = {w["kind"]: w for w in result["watermarks"]}
    assert sorted(by_kind) == ["kline"]
    kline = by_kind["kline"]
    # BTCUSDT 两个周期算 1 个标的
    assert kline["symbol_count"] == 2
    assert kline["total_rows"] == 2 + 3 + 2
    assert kline["earliest_date"] == "2025-01-01"
    assert kline["latest_date"] == "2026-11-19"
    assert kline["updated_at"] is None

    storage = {s["kind"]: s["bytes"] for s in result["storage"]}
    assert storage == {"kline": size_a + size_b + size_c}
    assert result["total_bytes"] == size_a + size_b + size_c


def test_get_watermark_pool_funding_rate_without_meta(tmp_path: Path):
    """fundingRate 无 meta 布局：行数与日期来自 parquet footer（毫秒时间戳）。"""
    ms = [1793894400000, 1793980800000]  # 2026-11-05 / 2026-11-06 UTC
    size = _write_parquet(tmp_path / "fundingRate" / "um" / "BTCUSDT" / "BTCUSDT-fundingRate-20261107.parquet", ms)
    other_ms = [1793462400000]  # 2026-10-31 UTC
    size += _write_parquet(
        tmp_path / "fundingRate" / "cm" / "LTCUSDT" / "LTCUSDT-fundingRate-20261107.parquet", other_ms
    )

    result = ArchiveService(base_dir=tmp_path).get_watermark()

    by_kind = {w["kind"]: w for w in result["watermarks"]}
    assert sorted(by_kind) == ["fundingRate"]
    assert by_kind["fundingRate"]["symbol_count"] == 2
    assert by_kind["fundingRate"]["total_rows"] == 3
    assert by_kind["fundingRate"]["earliest_date"] == "2026-10-31"
    assert by_kind["fundingRate"]["latest_date"] == "2026-11-06"
    assert {s["kind"]: s["bytes"] for s in result["storage"]} == {"fundingRate": size}


def test_get_watermark_meta_wins_over_parquet_in_same_dir(tmp_path: Path):
    """同一目录既有 _meta.json 又有 parquet：只按 meta 计一次（不重复叠加行数/日期），
    但体积仍然按真实文件累加。
    """
    sym = tmp_path / "um" / "aggTrades" / "BTCUSDT"
    _write_meta(sym, total_rows=1000, earliest_date="2024-01-01", latest_date="2024-03-05")
    size = _write_parquet(sym / "BTCUSDT-aggTrades-2024-03-05.parquet", [1709510400000, 1709596800000])

    result = ArchiveService(base_dir=tmp_path).get_watermark()

    by_kind = {w["kind"]: w for w in result["watermarks"]}
    assert by_kind["aggTrades"]["symbol_count"] == 1
    assert by_kind["aggTrades"]["total_rows"] == 1000  # 不是 1000 + 2
    assert by_kind["aggTrades"]["earliest_date"] == "2024-01-01"  # 不掺 parquet 的 2024-03-04
    assert by_kind["aggTrades"]["latest_date"] == "2024-03-05"
    assert {s["kind"]: s["bytes"] for s in result["storage"]} == {"aggTrades": size}


def test_get_watermark_pool_parquet_without_time_column_counts_rows_only(tmp_path: Path):
    """没有时间列（也没有 __index_level_0__）：行数照算，日期保持 None（不填今天）。"""
    import pyarrow as pa
    import pyarrow.parquet as pq

    path = tmp_path / "openInterest" / "um" / "LTCUSDT" / "LTCUSDT-openInterest-20261107.parquet"
    path.parent.mkdir(parents=True)
    pq.write_table(pa.table({"sumOpenInterest": pa.array(["1", "2"], type=pa.string())}), path)

    result = ArchiveService(base_dir=tmp_path).get_watermark()

    by_kind = {w["kind"]: w for w in result["watermarks"]}
    assert by_kind["openInterest"]["symbol_count"] == 1
    assert by_kind["openInterest"]["total_rows"] == 2
    assert by_kind["openInterest"]["earliest_date"] is None
    assert by_kind["openInterest"]["latest_date"] is None


# =================== get_symbol_coverage ===================


def test_get_symbol_coverage_merges_kline_meta_and_pool(tmp_path: Path):
    """单标的覆盖：K 线池（周期=目录名）与归档布局（meta + 文件名周期）合并，
    「累计 bar」只算 K 线类行数，成交/快照行不计入 bar。
    """
    base = tmp_path
    # 数据池 K 线：spot 的 1h / 15m
    _write_parquet(base / "crypto" / "spot" / "klines" / "1h" / "LTCUSDT.parquet", [1672531200000])
    _write_parquet(base / "crypto" / "spot" / "klines" / "15m" / "LTCUSDT.parquet", [1672531200000] * 3)
    # 同名标的的其他市场文件：spot 查询不能读到
    _write_parquet(base / "crypto" / "future" / "klines" / "1h" / "LTCUSDT.parquet", [1672531200000] * 5)
    # 归档布局：aggTrades 有 meta
    agg = base / "spot" / "aggTrades" / "LTCUSDT"
    _write_meta(agg, kind="aggTrades", total_rows=500, earliest_date="2024-02-01", latest_date="2024-02-03")
    (agg / "LTCUSDT-aggTrades-2024-02-03.parquet").touch()
    # 归档布局：标记价 K 线，周期从文件名解析（1h + 4h）
    mark = base / "spot" / "markPriceKlines" / "LTCUSDT"
    _write_meta(mark, kind="markPriceKlines", total_rows=24, latest_date="2024-02-04")
    (mark / "LTCUSDT-markPriceKlines-1h-2024-02-04.parquet").touch()
    (mark / "LTCUSDT-markPriceKlines-4h-2024-02-04.parquet").touch()
    # 数据池衍生：fundingRate 在 {kind}/{market}/{symbol} 层序
    _write_parquet(base / "fundingRate" / "spot" / "LTCUSDT" / "LTCUSDT-fundingRate-20240204.parquet", [1672531200000] * 2)
    # 不在本次查询范围的其他标的
    _write_parquet(base / "crypto" / "spot" / "klines" / "1h" / "ETHUSDT.parquet", [1672531200000] * 9)

    result = ArchiveService(base_dir=base).get_symbol_coverage("LTC/USDT", MarketType.SPOT)

    assert result["symbol"] == "LTCUSDT"
    assert result["market"] == "spot"
    by_kind = {item["kind"]: item for item in result["items"]}
    assert sorted(by_kind) == ["aggTrades", "fundingRate", "kline", "markPriceKlines"]
    # 周期按 15m → 1h → 4h 的规范顺序，不按字母序
    assert result["intervals"] == ["15m", "1h", "4h"]
    assert by_kind["kline"]["total_rows"] == 4
    assert by_kind["markPriceKlines"]["intervals"] == ["1h", "4h"]
    assert result["total_rows"] == 4 + 500 + 24 + 2
    # bar = K 线类（kline + markPriceKlines），成交/资金费行不计
    assert result["bar_rows"] == 4 + 24
    assert result["latest_date"] == "2024-02-04"


def test_get_symbol_coverage_empty_when_symbol_absent(tmp_path: Path):
    """没有任何落盘：items 空、bar_rows 0、intervals 空、日期 None（不编造今天）。"""
    result = ArchiveService(base_dir=tmp_path).get_symbol_coverage("NOPE/USDT", MarketType.SPOT)
    assert result["items"] == []
    assert result["total_rows"] == 0
    assert result["bar_rows"] == 0
    assert result["intervals"] == []
    assert result["latest_date"] is None


# =================== __init__ ===================


def test_archive_service_stores_base_dir_as_path():
    """__init__ 必须把 base_dir 规范成 Path 对象。"""
    svc = ArchiveService(base_dir="/tmp/qc", proxy=None)
    assert isinstance(svc.base_dir, Path)
    assert svc.proxy is None
