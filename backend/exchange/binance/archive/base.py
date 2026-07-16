"""7 种归档数据下载器的共享基类（独立实现，不继承 BaseCollector）。

子类必须重写 4 个类属性钩子:
    archive_kind, url_subpath, column_mapping, parquet_schema
子类可选重写方法:
    transform_df, needs_unzip, _parse_csv_bytes
"""
from __future__ import annotations

import io
import logging
import shutil
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable

import aiohttp
import pandas as pd

from exchange.binance.archive.archive_meta import write_meta
from exchange.binance.archive.kinds import (
    ArchiveKind,
    MarketType,
    build_zip_url,
    get_save_dir,
)

logger = logging.getLogger(__name__)

# 磁盘预警阈值：剩余空间小于 5GB 时停止（spec §6.2）
_DISK_FREE_MIN_BYTES = 5 * 1024 ** 3

# 单次 read_range 硬上限 1M 行（spec §5.1）
_READ_RANGE_MAX_ROWS = 1_000_000


class BaseBinanceArchiveDownloader:
    """所有 7 种归档数据的下载器基类（独立实现，不继承 BaseCollector）。"""

    # —— 子类必须重写 ——
    archive_kind: ArchiveKind
    url_subpath: str
    column_mapping: dict[str, str]
    parquet_schema: object | None  # pyarrow.Schema, None = 推断

    # —— 子类可选重写 ——
    def transform_df(self, raw_df: pd.DataFrame) -> pd.DataFrame:
        return raw_df

    def needs_unzip(self) -> bool:
        return True

    def _parse_csv_bytes(self, data: bytes) -> pd.DataFrame:
        """子类可重写以适配无 header / 不同分隔符的 zip。"""
        return pd.read_csv(io.BytesIO(data))

    # —— 构造 ——
    def __init__(
        self,
        market: MarketType,
        base_dir: str | Path,
        symbol: str,
        interval: str | None = None,
        proxy: str | None = None,
    ) -> None:
        self.market = market
        self.base_dir = Path(base_dir)
        self.interval = interval
        self.proxy = proxy
        # save_dir 依赖具体 symbol；可在 collect_data 期间通过 bind_symbol 切换
        self._symbol: str | None = symbol
        self.save_dir: Path = get_save_dir(self.base_dir, market, self.archive_kind, symbol)

    # —— URL 拼装 ——
    def get_zip_url(self, symbol: str, date_str: str) -> str:
        return build_zip_url(self.market, self.archive_kind, symbol, date_str, self.interval)

    def get_zip_name(self, symbol: str, date_str: str) -> str:
        interval_seg = f'{self.interval}-' if self.interval else ''
        return f'{symbol}-{self.archive_kind.value}-{interval_seg}{date_str}.zip'

    # —— HTTP 下载（异步） ——
    async def get_daily_archive(
        self, session: aiohttp.ClientSession, symbol: str, day: date
    ) -> pd.DataFrame:
        """下载某日 zip → 解压 → 解析 CSV → 转换列名 → 返回 DataFrame。"""
        date_str = day.isoformat()
        url = self.get_zip_url(symbol, date_str)
        logger.info("Downloading %s", url)

        # 磁盘预警
        check_dir = self.save_dir if self.save_dir.exists() else self.base_dir
        if check_dir.exists() and shutil.disk_usage(check_dir).free < _DISK_FREE_MIN_BYTES:
            raise IOError(f"Less than 5GB free disk space, aborting {symbol} {date_str}")

        timeout = aiohttp.ClientTimeout(total=300)
        async with session.get(url, proxy=self.proxy, timeout=timeout) as resp:
            if resp.status == 404:
                logger.info("%s: %s not found, skip", symbol, date_str)
                return pd.DataFrame()
            resp.raise_for_status()
            data = await resp.read()

        if not self.needs_unzip():
            return self.transform_df(self._parse_csv_bytes(data))

        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            csv_name = next((n for n in zf.namelist() if n.endswith('.csv')), None)
            if csv_name is None:
                logger.warning("%s: zip has no CSV: %s", symbol, zf.namelist())
                return pd.DataFrame()
            with zf.open(csv_name) as f:
                raw_df = self.transform_df(self._parse_csv_bytes(f.read()))
        return raw_df

    # —— 缺失区间计算 ——
    def _calculate_missing_ranges(
        self, start: date, end: date, mode: str
    ) -> list[tuple[date, date]]:
        """返回 (start, end) 区间列表。

        - inc: 跳过已有 parquet 文件
        - full: 重下所有日期
        """
        if not self.save_dir.exists():
            return [(start, end)]

        if mode == 'full':
            return [
                (start + timedelta(days=i), start + timedelta(days=i))
                for i in range((end - start).days + 1)
            ]

        # inc
        existing: set[date] = set()
        for p in self.save_dir.glob('*.parquet'):
            try:
                stem = p.stem
                date_part = stem.split('-')[-3:]
                d = date(int(date_part[0]), int(date_part[1]), int(date_part[2]))
                existing.add(d)
            except (ValueError, IndexError):
                continue

        missing: list[tuple[date, date]] = []
        cur = start
        while cur <= end:
            if cur not in existing:
                missing.append((cur, cur))
            cur += timedelta(days=1)
        return missing

    # —— 写入 Parquet ——
    def save_instrument(self, symbol: str, day: date, df: pd.DataFrame) -> Path | None:
        if df.empty:
            return None
        self.save_dir.mkdir(parents=True, exist_ok=True)
        interval_seg = f'{self.interval}-' if self.interval else ''
        out_path = (
            self.save_dir
            / f'{symbol}-{self.archive_kind.value}-{interval_seg}{day.isoformat()}.parquet'
        )
        df.to_parquet(out_path, engine='pyarrow', compression='snappy', index=False)
        logger.info("Saved %s (%d rows)", out_path.name, len(df))
        return out_path

    # —— 顶层入口（多 symbols 顺序下载） ——
    def collect_data(
        self,
        symbols: list[str],
        start: str,
        end: str,
        mode: str = 'inc',
        progress_cb: Callable[[int, int], None] | None = None,
    ) -> dict:
        if not symbols:
            return {'files_added': 0, 'symbols_processed': 0}

        start_d = date.fromisoformat(start)
        end_d = date.fromisoformat(end)
        files_added = 0
        symbols_processed = 0

        for sym in symbols:
            self._symbol = sym
            self.save_dir = get_save_dir(self.base_dir, self.market, self.archive_kind, sym)
            ranges = self._calculate_missing_ranges(start_d, end_d, mode)
            for s, e in ranges:
                day = s
                while day <= e:
                    try:
                        df = self._run_async(self.get_daily_archive, sym, day)
                        path = self.save_instrument(sym, day, df)
                        if path is not None:
                            files_added += 1
                        write_meta(self.save_dir, sym, self.archive_kind, self.market, day)
                    except Exception as exc:
                        logger.exception("Failed %s %s: %s", sym, day, exc)
                    if progress_cb:
                        progress_cb(symbols_processed, files_added)
                    day += timedelta(days=1)
            symbols_processed += 1
        return {'files_added': files_added, 'symbols_processed': symbols_processed}

    # —— 读区间（前端查询入口，spec §5.2） ——
    def read_range(
        self, symbol: str, start_time: int, end_time: int, limit: int, offset: int
    ) -> dict:
        self._symbol = symbol
        self.save_dir = get_save_dir(self.base_dir, self.market, self.archive_kind, symbol)
        if not self.save_dir.exists():
            return {'total': 0, 'rows': [], 'truncated': False}

        target_files: list[Path] = []
        for p in sorted(self.save_dir.glob('*.parquet')):
            try:
                stem = p.stem
                date_part = stem.split('-')[-3:]
                d = date(int(date_part[0]), int(date_part[1]), int(date_part[2]))
                day_ms = int(datetime(d.year, d.month, d.day).timestamp() * 1000)
                if start_time <= day_ms + 86_400_000 <= end_time + 86_400_000:
                    target_files.append(p)
            except (ValueError, IndexError):
                continue

        if not target_files:
            return {'total': 0, 'rows': [], 'truncated': False}

        df = pd.concat([pd.read_parquet(p) for p in target_files], ignore_index=True)
        total = len(df)
        truncated = False
        if total > _READ_RANGE_MAX_ROWS:
            df = df.head(_READ_RANGE_MAX_ROWS)
            truncated = True
        df = df.iloc[offset:offset + limit]
        return {'total': total, 'rows': df.to_dict(orient='records'), 'truncated': truncated}

    def _run_async(self, coro_func, *args) -> object:
        """同步入口里驱动单次异步调用（asyncio.run）。"""
        import asyncio
        return asyncio.run(coro_func(*args))
