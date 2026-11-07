"""下载链路并发化单测：日期层 / symbol 层 / interval 与归档层 / 参数穿透"""

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from collector.utils.task_manager import task_manager
from exchange.base import BaseCollector
from exchange.binance.downloader import BinanceDownloader


def _make_downloader(tmp_path: Path, max_workers: int) -> BinanceDownloader:
    return BinanceDownloader(
        save_dir=tmp_path,
        candle_type="spot",
        start="2024-01-01",
        end="2024-01-10",
        interval="1d",
        max_workers=max_workers,
        symbols=["BTCUSDT"],
        mode="inc",
    )


class TestDownloadDailyKlinesConcurrency:
    """日期层：Semaphore 并发 + gather 保序 + 进度单调 + T+1 跳过"""

    def _install_fake_klines(self, monkeypatch, holder: dict):
        """替换 get_daily_klines 为受控异步假实现，记录并发峰值与调用"""
        in_flight = {"n": 0}

        async def fake_get_daily_klines(self, symbol, timeframe, date):
            in_flight["n"] += 1
            holder["peak"] = max(holder.get("peak", 0), in_flight["n"])
            holder.setdefault("calls", []).append(date)
            await asyncio.sleep(0.05)
            in_flight["n"] -= 1
            # open_time 用 YYYYMMDD 整数，天然按日期可比大小
            return pd.DataFrame({"open_time": [int(date.replace("-", ""))], "close": [1.0]})

        monkeypatch.setattr(BinanceDownloader, "get_daily_klines", fake_get_daily_klines)

    def test_concurrent_peak_and_order(self, tmp_path, monkeypatch):
        holder: dict = {}
        self._install_fake_klines(monkeypatch, holder)
        dl = _make_downloader(tmp_path, max_workers=4)
        progress: list[int] = []

        df = asyncio.run(
            dl.download_daily_klines(
                "BTCUSDT",
                "1d",
                "2024-01-01",
                "2024-01-10",
                lambda s, c, t, st: progress.append(c),
            )
        )

        assert len(df) == 10
        assert progress == list(range(1, 11))  # 进度单调递增且完备
        assert holder["peak"] >= 2  # 确实并发了
        assert holder["peak"] <= 4  # 不超过上限
        assert df["open_time"].tolist() == sorted(df["open_time"].tolist())  # gather 保序

    def test_t_plus_one_archive_skipped(self, tmp_path, monkeypatch):
        holder: dict = {}
        self._install_fake_klines(monkeypatch, holder)
        tomorrow = (datetime.now(UTC).date() + timedelta(days=1)).strftime("%Y-%m-%d")
        dl = _make_downloader(tmp_path, max_workers=4)
        progress: list[int] = []

        df = asyncio.run(
            dl.download_daily_klines(
                "BTCUSDT",
                "1d",
                tomorrow,
                tomorrow,
                lambda s, c, t, st: progress.append(c),
            )
        )

        assert holder.get("calls", []) == []  # 未发出下载请求
        assert progress == [1]  # 进度仍照常推进
        assert df.empty


def test_task_manager_update_progress_thread_safe():
    """16 线程并发更新进度不炸不丢（update_progress 内含 DB 写与 WS 广播）"""
    task_id = task_manager.create_task(
        task_type="unit_test",
        exchange="binance",
        start="2024-01-01",
        end="2024-01-02",
        interval="1d",
        max_workers=4,
        candle_type="spot",
        symbols=["BTCUSDT"],
        save_dir=None,
        data_type="kline",
        market="spot",
    )

    def update(i: int) -> bool:
        return task_manager.update_progress(
            task_id=task_id,
            current=f"S{i}",
            completed=i,
            total=64,
            status=f"t{i}",
            symbol_progress=float(i),
            interval="1d",
        )

    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(update, range(64)))

    assert all(results)
