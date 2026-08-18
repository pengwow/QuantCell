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


def test_list_symbols_returns_sorted_subdirs(tmp_path: Path):
    """list_symbols 扫描 market/kind 下子目录, 按字典序排序。"""
    base = tmp_path
    spot = base / "spot" / "aggTrades"
    spot.mkdir(parents=True)
    (spot / "BTCUSDT").mkdir()
    (spot / "ETHUSDT").mkdir()
    (spot / "ADAUSDT").mkdir()
    # 放个文件, 不应被识别为 symbol
    (spot / "readme.txt").write_text("not a dir")

    svc = ArchiveService(base_dir=base)
    result = svc.list_symbols(ArchiveKind.AGG_TRADES, MarketType.SPOT)
    assert result == ["ADAUSDT", "BTCUSDT", "ETHUSDT"]


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


# =================== __init__ ===================


def test_archive_service_stores_base_dir_as_path():
    """__init__ 必须把 base_dir 规范成 Path 对象。"""
    svc = ArchiveService(base_dir="/tmp/qc", proxy=None)
    assert isinstance(svc.base_dir, Path)
    assert svc.proxy is None
