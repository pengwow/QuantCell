# Binance 历史归档（Tick + K 线）全种类数据采集实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 QuantCell 数据管理模块新增 7 种 Binance 历史归档数据（aggTrades / trades / bookDepth / bookTicker / markPriceKlines / indexPriceKlines / premiumIndexKlines）跨 3 个市场（spot / futures/um / futures/cm）的采集能力，全部只入 Parquet 分区，不动现有 K 线数据流。

**Architecture:** 新建 `backend/exchange/binance/archive/` 子包，提供 1 个基类（90% 通用逻辑）+ 7 个轻量 fetcher（仅重写 4 个钩子）+ 1 个工厂装配 7×3=21 组合。复用现有 `BaseCollector` / `task_manager` / `scheduled_tasks` / `parquet_utils` 基础设施。`backend/collector/services/archive_service.py` 做业务编排，`backend/collector/api/archive.py` 提供 6 个 REST 端点。前端 `DataCollectionPage` 加 kind 多选 + market 单选；`DataManagementPage` 新增归档浏览 tab。`quantcell data archive ...` CLI 子命令。

**Tech Stack:** Python 3.12, pandas, pyarrow, FastAPI, typer (CLI), pytest, aiohttp, React + TypeScript + bun

**Spec:** [docs/superpowers/specs/2026-07-16-binance-archive-tick-data-design.md](../../specs/2026-07-16-binance-archive-tick-data-design.md)

---

## 文件结构总览

### 新建文件

```
backend/exchange/binance/archive/
├── __init__.py                        # 导出工厂 + 枚举
├── kinds.py                           # ArchiveKind / MarketType 枚举、列名常量
├── base.py                            # BaseBinanceArchiveDownloader
├── factory.py                         # BinanceArchiveFactory
├── archive_meta.py                    # _meta.json 读写
└── fetchers/
    ├── __init__.py
    ├── agg_trades.py
    ├── trades.py
    ├── book_depth.py
    ├── book_ticker.py
    ├── mark_price_klines.py
    ├── index_price_klines.py
    └── premium_index_klines.py

backend/collector/
├── services/
│   ├── archive_service.py             # 业务编排
│   └── archive_meta_service.py        # 元数据查询
├── api/
│   └── archive.py                     # 6 个 REST 端点
└── db/
    └── archive_task.py                # 任务类型枚举扩展（注册到 scheduled_tasks）

backend/cli/data.py                    # 追加 archive subcommand（在已有文件上扩展）

backend/tests/
├── unit/exchange/binance/archive/
│   ├── test_kinds.py
│   ├── test_base_archive.py
│   ├── test_factory.py
│   ├── test_meta.py
│   └── fetchers/
│       ├── test_agg_trades.py
│       ├── test_trades.py
│       ├── test_book_depth.py
│       ├── test_book_ticker.py
│       ├── test_mark_klines.py
│       ├── test_index_klines.py
│       └── test_premium_klines.py
├── integration/
│   └── test_archive_api.py
└── fixtures/
    └── archive_zip/
        ├── BTCUSDT-aggTrades-2024-12-01.zip
        ├── BTCUSDT-trades-2024-12-01.zip
        ├── BTCUSDT-bookDepth-2024-12-01.zip
        └── ...（7 种各 1 个 fixture，录制自 data.binance.vision）

backend/scripts/
└── check_archive.py                   # self-check demo

frontend/src/
├── api/
│   └── dataApi.ts                     # 追加 archiveApi
├── types/
│   └── data.ts                        # 追加 ArchiveKind / MarketType / ArchiveRow
└── pages/data/
    ├── DataCollectionPage.tsx         # 任务对话框加多选
    └── DataManagementPage.tsx         # 新增归档浏览 tab
```

### 修改文件

```
backend/cli/__init__.py                # 注册 archive subcommand
backend/collector/db/models.py         # 扩展 ScheduledTask.task_type 枚举（不动表结构）
backend/collector/api/__init__.py     # 注册 archive router
backend/collector/services/__init__.py # 暴露 archive_service
```

---

## Task 1: 枚举与 URL 拼装工具（kinds.py）

**Files:**
- Create: `backend/exchange/binance/archive/__init__.py`
- Create: `backend/exchange/binance/archive/kinds.py`
- Test: `backend/tests/unit/exchange/binance/archive/test_kinds.py`

**目标:** 定义 `ArchiveKind` / `MarketType` 枚举 + URL 拼装纯函数（无 I/O）。

- [ ] **Step 1: 写测试**

```python
# backend/tests/unit/exchange/binance/archive/test_kinds.py
from exchange.binance.archive.kinds import (
    ArchiveKind, MarketType, build_zip_url, get_save_dir, KIND_INTERVALS,
)


def test_archive_kind_enum_has_7_values():
    assert len(ArchiveKind) == 7
    assert ArchiveKind.AGG_TRADES.value == 'aggTrades'
    assert ArchiveKind.TRADES.value == 'trades'
    assert ArchiveKind.BOOK_DEPTH.value == 'bookDepth'
    assert ArchiveKind.BOOK_TICKER.value == 'bookTicker'
    assert ArchiveKind.MARK_KLINES.value == 'markPriceKlines'
    assert ArchiveKind.INDEX_KLINES.value == 'indexPriceKlines'
    assert ArchiveKind.PREMIUM_KLINES.value == 'premiumIndexKlines'


def test_market_type_enum_has_3_values():
    assert len(MarketType) == 3
    assert MarketType.SPOT.value == 'spot'
    assert MarketType.FUTURES_UM.value == 'um'
    assert MarketType.FUTURES_CM.value == 'cm'


def test_kinds_that_need_interval():
    assert KIND_INTERVALS[ArchiveKind.MARK_KLINES] == ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '1d']
    assert KIND_INTERVALS[ArchiveKind.INDEX_KLINES] == ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '1d']
    assert KIND_INTERVALS[ArchiveKind.PREMIUM_KLINES] == ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '1d']
    assert KIND_INTERVALS[ArchiveKind.AGG_TRADES] is None
    assert KIND_INTERVALS[ArchiveKind.TRADES] is None
    assert KIND_INTERVALS[ArchiveKind.BOOK_DEPTH] is None
    assert KIND_INTERVALS[ArchiveKind.BOOK_TICKER] is None


def test_build_zip_url_spot_aggtrades():
    url = build_zip_url(MarketType.SPOT, ArchiveKind.AGG_TRADES, 'BTCUSDT', '2024-12-01')
    assert url == 'https://data.binance.vision/data/spot/daily/aggTrades/BTCUSDT/BTCUSDT-aggTrades-2024-12-01.zip'


def test_build_zip_url_um_mark_klines_with_interval():
    url = build_zip_url(MarketType.FUTURES_UM, ArchiveKind.MARK_KLINES, 'BTCUSDT', '2024-12-01', interval='1h')
    assert url == 'https://data.binance.vision/data/futures/um/daily/markPriceKlines/BTCUSDT/1h/BTCUSDT-markPriceKlines-1h-2024-12-01.zip'


def test_build_zip_url_cm_book_depth():
    url = build_zip_url(MarketType.FUTURES_CM, ArchiveKind.BOOK_DEPTH, 'BTCUSD', '2024-12-01')
    assert url == 'https://data.binance.vision/data/futures/cm/daily/bookDepth/BTCUSD/BTCUSD-bookDepth-2024-12-01.zip'


def test_get_save_dir_spot():
    base = '/tmp/qc'
    d = get_save_dir(base, MarketType.SPOT, ArchiveKind.AGG_TRADES, 'BTCUSDT')
    assert d == '/tmp/qc/spot/aggTrades/BTCUSDT'
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/exchange/binance/archive/test_kinds.py -v`
Expected: `ModuleNotFoundError: No module named 'exchange.binance.archive.kinds'`

- [ ] **Step 3: 创建包目录与 `kinds.py`**

```python
# backend/exchange/binance/archive/__init__.py
"""Binance 历史归档（Tick + K 线）下载体系。

7 种数据 × 3 个市场，全部只入 Parquet 分区。
"""

from exchange.binance.archive.kinds import (
    ArchiveKind,
    MarketType,
    build_zip_url,
    get_save_dir,
    KIND_INTERVALS,
)
from exchange.binance.archive.factory import BinanceArchiveFactory

__all__ = [
    "ArchiveKind",
    "MarketType",
    "build_zip_url",
    "get_save_dir",
    "KIND_INTERVALS",
    "BinanceArchiveFactory",
]
```

```python
# backend/exchange/binance/archive/kinds.py
"""Binance 历史归档枚举与 URL 拼装工具。"""
from __future__ import annotations

from enum import Enum
from pathlib import Path

# —— 7 种归档数据种类 ——
class ArchiveKind(str, Enum):
    AGG_TRADES = 'aggTrades'
    TRADES = 'trades'
    BOOK_DEPTH = 'bookDepth'
    BOOK_TICKER = 'bookTicker'
    MARK_KLINES = 'markPriceKlines'
    INDEX_KLINES = 'indexPriceKlines'
    PREMIUM_KLINES = 'premiumIndexKlines'


# —— 3 个市场 ——
class MarketType(str, Enum):
    SPOT = 'spot'
    FUTURES_UM = 'um'
    FUTURES_CM = 'cm'


# —— 市场到 Binance URL 路径前缀 ——
_MARKET_URL_PREFIX: dict[MarketType, str] = {
    MarketType.SPOT: 'data/spot',
    MarketType.FUTURES_UM: 'data/futures/um',
    MarketType.FUTURES_CM: 'data/futures/cm',
}


# —— K 线类支持的 interval（spec §3.4）——
KIND_INTERVALS: dict[ArchiveKind, list[str] | None] = {
    ArchiveKind.AGG_TRADES: None,
    ArchiveKind.TRADES: None,
    ArchiveKind.BOOK_DEPTH: None,
    ArchiveKind.BOOK_TICKER: None,
    ArchiveKind.MARK_KLINES: ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '1d'],
    ArchiveKind.INDEX_KLINES: ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '1d'],
    ArchiveKind.PREMIUM_KLINES: ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '1d'],
}


def build_zip_url(
    market: MarketType,
    kind: ArchiveKind,
    symbol: str,
    date_str: str,
    interval: str | None = None,
) -> str:
    """拼装 Binance 官方归档 zip 的下载 URL。

    Examples:
        >>> build_zip_url(MarketType.SPOT, ArchiveKind.AGG_TRADES, 'BTCUSDT', '2024-12-01')
        'https://data.binance.vision/data/spot/daily/aggTrades/BTCUSDT/BTCUSDT-aggTrades-2024-12-01.zip'
    """
    prefix = _MARKET_URL_PREFIX[market]
    parts = [f'https://data.binance.vision/{prefix}/daily/{kind.value}/{symbol}']
    if interval is not None:
        parts.append(interval)
    parts.append(f'{symbol}-{kind.value}-{interval + "-" if interval else ""}{date_str}.zip')
    return '/'.join(parts[:-1]) + '/' + parts[-1]


def get_save_dir(
    base_dir: str | Path,
    market: MarketType,
    kind: ArchiveKind,
    symbol: str,
) -> Path:
    """返回某 (market, kind, symbol) 的本地存储目录。

    Example: '/tmp/qc/spot/aggTrades/BTCUSDT'
    """
    return Path(base_dir) / market.value / kind.value / symbol
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/exchange/binance/archive/test_kinds.py -v`
Expected: 7 passed

- [ ] **Step 5: 提交**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add backend/exchange/binance/archive/ backend/tests/unit/exchange/binance/archive/test_kinds.py
git commit -m "feat(archive): add kinds enum + URL builder for 7 archive types × 3 markets"
```

---

## Task 2: 抽象基类 `BaseBinanceArchiveDownloader`

**Files:**
- Create: `backend/exchange/binance/archive/base.py`
- Test: `backend/tests/unit/exchange/binance/archive/test_base_archive.py`

**目标:** 提供 90% 通用下载逻辑（URL 拼装、HTTP 下载、解压、Parquet 写入、增量/全量、并发、元数据更新），子类只重写 4 个钩子。

> **调整说明（2026-07-16 critical review）**：原 plan 假设继承 `collector.base_collector.BaseCollector` 并提供 `proxy` 参数。实际 `BaseCollector` 在 `exchange.base`，且是按"逐 instrument + 区间"模式设计（抽象方法 `get_instrument_list` / `normalize_symbol` / `get_data`），与本归档"逐日 zip"模式不匹配。**改为独立基类，不继承 BaseCollector**。7 个 fetcher 接口保持不变。

- [ ] **Step 1: 写测试**

```python
# backend/tests/unit/exchange/binance/archive/test_base_archive.py
from datetime import date
from pathlib import Path
import pandas as pd
import pytest
from exchange.binance.archive.kinds import ArchiveKind, MarketType
from exchange.binance.archive.base import BaseBinanceArchiveDownloader


# 测试用最小 fetcher，重写 4 个钩子
class _StubFetcher(BaseBinanceArchiveDownloader):
    archive_kind = ArchiveKind.AGG_TRADES
    url_subpath = 'aggTrades'
    column_mapping = {'a': 'price', 'b': 'qty'}
    parquet_schema = None  # 走默认推断

    def transform_df(self, raw_df: pd.DataFrame) -> pd.DataFrame:
        return raw_df.rename(columns={'a': 'price', 'b': 'qty'})


def test_init_resolves_save_dir(tmp_path):
    fetcher = _StubFetcher(market=MarketType.SPOT, base_dir=tmp_path, interval=None)
    assert fetcher.save_dir == tmp_path / 'spot' / 'aggTrades' / 'BTCUSDT'
    assert fetcher.market == MarketType.SPOT


def test_get_zip_url_calls_kinds_builder(tmp_path):
    fetcher = _StubFetcher(market=MarketType.SPOT, base_dir=tmp_path, interval=None)
    url = fetcher.get_zip_url('BTCUSDT', '2024-12-01')
    assert 'data.binance.vision/data/spot/daily/aggTrades/BTCUSDT' in url
    assert '2024-12-01.zip' in url


def test_calculate_missing_ranges_full_mode_includes_all(tmp_path):
    fetcher = _StubFetcher(market=MarketType.SPOT, base_dir=tmp_path, interval=None)
    fetcher.save_dir.mkdir(parents=True, exist_ok=True)
    # 已有 2024-12-02 文件
    (fetcher.save_dir / 'BTCUSDT-aggTrades-2024-12-02.parquet').touch()

    ranges = fetcher._calculate_missing_ranges(
        start=date(2024, 12, 1), end=date(2024, 12, 3), mode='full'
    )
    # full 模式：忽略已有，重下全部
    assert len(ranges) == 3
    assert ranges[0] == (date(2024, 12, 1), date(2024, 12, 1))
    assert ranges[-1] == (date(2024, 12, 3), date(2024, 12, 3))


def test_calculate_missing_ranges_inc_mode_skips_existing(tmp_path):
    fetcher = _StubFetcher(market=MarketType.SPOT, base_dir=tmp_path, interval=None)
    fetcher.save_dir.mkdir(parents=True, exist_ok=True)
    (fetcher.save_dir / 'BTCUSDT-aggTrades-2024-12-02.parquet').touch()

    ranges = fetcher._calculate_missing_ranges(
        start=date(2024, 12, 1), end=date(2024, 12, 3), mode='inc'
    )
    # inc 模式：跳过 12-02
    flat = [d for r in ranges for d in r]
    assert flat == [date(2024, 12, 1), date(2024, 12, 3)]


def test_read_range_with_no_files_returns_empty(tmp_path):
    fetcher = _StubFetcher(market=MarketType.SPOT, base_dir=tmp_path, interval=None)
    result = fetcher.read_range(
        symbol='BTCUSDT', start_time=1700000000000, end_time=1800000000000, limit=100, offset=0
    )
    assert result['total'] == 0
    assert result['rows'] == []


def test_collect_data_no_symbols_returns_empty(tmp_path):
    fetcher = _StubFetcher(market=MarketType.SPOT, base_dir=tmp_path, interval=None)
    result = fetcher.collect_data(symbols=[], start='2024-12-01', end='2024-12-02', mode='inc')
    assert result == {'files_added': 0, 'symbols_processed': 0}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/exchange/binance/archive/test_base_archive.py -v`
Expected: `ModuleNotFoundError: No module named 'exchange.binance.archive.base'`

- [ ] **Step 3: 实现基类**

```python
# backend/exchange/binance/archive/base.py
"""7 种归档数据下载器的共享基类。

子类必须重写 4 个类属性钩子:
    archive_kind, url_subpath, column_mapping, parquet_schema
子类可选重写方法:
    transform_df, needs_unzip
"""
from __future__ import annotations

import io
import logging
import shutil
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Iterable

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

# 磁盘预警阈值：剩余空间小于 5GB 时停止
_DISK_FREE_MIN_BYTES = 5 * 1024 ** 3


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
    async def get_daily_archive(self, session: aiohttp.ClientSession, symbol: str, day: date) -> pd.DataFrame:
        """下载某日 zip → 解压 → 解析 CSV → 转换列名 → 返回 DataFrame。"""
        date_str = day.isoformat()
        url = self.get_zip_url(symbol, date_str)
        logger.info("Downloading %s", url)

        # 磁盘预警
        if shutil.disk_usage(self.save_dir if self.save_dir.exists() else self.base_dir).free < _DISK_FREE_MIN_BYTES:
            raise IOError(f"Less than 5GB free disk space, aborting {symbol} {date_str}")

        timeout = aiohttp.ClientTimeout(total=300)
        async with session.get(url, proxy=self.proxy, timeout=timeout) as resp:
            if resp.status == 404:
                logger.info("%s: %s not found, skip", symbol, date_str)
                return pd.DataFrame()
            resp.raise_for_status()
            data = await resp.read()

        if not self.needs_unzip():
            return self._parse_csv_bytes(data)

        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            csv_name = next((n for n in zf.namelist() if n.endswith('.csv')), None)
            if csv_name is None:
                logger.warning("%s: zip has no CSV: %s", symbol, zf.namelist())
                return pd.DataFrame()
            with zf.open(csv_name) as f:
                raw_df = self._parse_csv_bytes(f.read())

        return self.transform_df(raw_df)

    def _parse_csv_bytes(self, data: bytes) -> pd.DataFrame:
        """子类可重写以适配无 header / 不同分隔符的 zip。"""
        return pd.read_csv(io.BytesIO(data))

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
            return [(start + timedelta(days=i), start + timedelta(days=i))
                    for i in range((end - start).days + 1)]

        # inc
        existing: set[date] = set()
        for p in self.save_dir.glob('*.parquet'):
            try:
                stem = p.stem  # e.g. BTCUSDT-aggTrades-2024-12-01
                date_part = stem.split('-')[-3:]  # 取最后三段 [YYYY, MM, DD]
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
        out_path = self.save_dir / f'{symbol}-{self.archive_kind.value}-{interval_seg}{day.isoformat()}.parquet'
        df.to_parquet(out_path, engine='pyarrow', compression='snappy', index=False)
        logger.info("Saved %s (%d rows)", out_path.name, len(df))
        return out_path

    # —— 顶层入口（多 symbols 顺序下载；并发由 BaseCollector 内部管理） ——
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

        # 顺序执行（max_workers=1, Windows pickle 限制）
        for sym in symbols:
            # 重新绑定 save_dir
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
                        # 更新元数据
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

        # 找到时间区间内的 parquet（按文件名日期筛选）
        target_files: list[Path] = []
        for p in sorted(self.save_dir.glob('*.parquet')):
            try:
                stem = p.stem
                date_part = stem.split('-')[-3:]
                d = date(int(date_part[0]), int(date_part[1]), int(date_part[2]))
                day_ms = int(datetime(d.year, d.month, d.day).timestamp() * 1000)
                if start_time <= day_ms + 86400000 <= end_time + 86400000:
                    target_files.append(p)
            except (ValueError, IndexError):
                continue

        if not target_files:
            return {'total': 0, 'rows': [], 'truncated': False}

        df = pd.concat([pd.read_parquet(p) for p in target_files], ignore_index=True)
        total = len(df)
        truncated = False
        if total > 1_000_000:  # spec §5.1 硬上限
            df = df.head(1_000_000)
            truncated = True
        df = df.iloc[offset:offset + limit]
        return {'total': total, 'rows': df.to_dict(orient='records'), 'truncated': truncated}

    def _run_async(self, coro_func, *args) -> object:
        """同步调用基类的异步方法（兼容现有 collect_data 是同步签名）。"""
        import asyncio
        return asyncio.run(coro_func(*args))
```

> **实现说明**：`_run_async` 这里用 `asyncio.run` 在同步入口里驱动单次异步调用；如果上层调用方已经在 event loop 里（比如 FastAPI handler），需要替换成 `asyncio.get_event_loop().run_until_complete` 或交给上层直接 await。**为简化接口，Task 2 阶段先用 `asyncio.run`；Task 12 接入业务编排时再调整**。

- [ ] **Step 4: 创建 `archive_meta.py` 桩（避免 Task 2 报 ImportError）**

```python
# backend/exchange/binance/archive/archive_meta.py
"""_meta.json 读写。Task 4 完整实现，本 task 提供桩以让 import 通过。"""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from exchange.binance.archive.kinds import ArchiveKind, MarketType


def write_meta(save_dir: Path, symbol: str, kind: ArchiveKind, market: MarketType, day) -> None:
    """Task 4 完整实现，本 task 提供占位（确保 import 通过即可）。"""
    meta_path = save_dir / '_meta.json'
    if not meta_path.exists():
        meta = {
            'symbol': symbol, 'kind': kind.value, 'market': market.value,
            'earliest_date': day.isoformat(), 'latest_date': day.isoformat(),
            'total_rows': 0, 'file_count': 0, 'corrupt_dates': [],
            'updated_at': datetime.now().astimezone().isoformat(),
        }
        save_dir.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2))


def read_meta(save_dir: Path) -> dict | None:
    meta_path = save_dir / '_meta.json'
    if not meta_path.exists():
        return None
    return json.loads(meta_path.read_text())
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/exchange/binance/archive/test_base_archive.py -v`
Expected: 6 passed

- [ ] **Step 6: 提交**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add backend/exchange/binance/archive/base.py backend/exchange/binance/archive/archive_meta.py backend/tests/unit/exchange/binance/archive/test_base_archive.py
git commit -m "feat(archive): BaseBinanceArchiveDownloader with 6-arg TDD coverage"
```

---

## Task 3: 工厂 `BinanceArchiveFactory`

**Files:**
- Create: `backend/exchange/binance/archive/factory.py`
- Test: `backend/tests/unit/exchange/binance/archive/test_factory.py`

- [ ] **Step 1: 写测试**

```python
# backend/tests/unit/exchange/binance/archive/test_factory.py
from exchange.binance.archive.factory import BinanceArchiveFactory
from exchange.binance.archive.kinds import ArchiveKind, MarketType
from exchange.binance.archive.fetchers.agg_trades import AggTradesFetcher
from exchange.binance.archive.fetchers.trades import TradesFetcher
from exchange.binance.archive.fetchers.book_ticker import BookTickerFetcher
from exchange.binance.archive.fetchers.mark_price_klines import MarkPriceKlinesFetcher


def test_factory_returns_correct_fetcher_per_kind():
    f = BinanceArchiveFactory.create(ArchiveKind.AGG_TRADES, MarketType.SPOT, base_dir='/tmp', symbol='BTCUSDT')
    assert isinstance(f, AggTradesFetcher)
    assert f.market == MarketType.SPOT


def test_factory_trades_returns_trades_fetcher():
    f = BinanceArchiveFactory.create(ArchiveKind.TRADES, MarketType.SPOT, base_dir='/tmp', symbol='BTCUSDT')
    assert isinstance(f, TradesFetcher)


def test_factory_book_ticker():
    f = BinanceArchiveFactory.create(ArchiveKind.BOOK_TICKER, MarketType.FUTURES_UM, base_dir='/tmp', symbol='BTCUSDT')
    assert isinstance(f, BookTickerFetcher)
    assert f.market == MarketType.FUTURES_UM


def test_factory_mark_klines_passes_interval():
    f = BinanceArchiveFactory.create(ArchiveKind.MARK_KLINES, MarketType.SPOT, base_dir='/tmp', symbol='BTCUSDT', interval='1h')
    assert isinstance(f, MarkPriceKlinesFetcher)
    assert f.interval == '1h'


def test_factory_unknown_kind_raises():
    import pytest
    with pytest.raises(ValueError):
        BinanceArchiveFactory.create('not_a_kind', MarketType.SPOT, base_dir='/tmp', symbol='BTCUSDT')
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/exchange/binance/archive/test_factory.py -v`
Expected: `ModuleNotFoundError: No module named 'exchange.binance.archive.factory'`

- [ ] **Step 3: 暂存 fetcher 桩（7 个，让 import 通过）**

```python
# backend/exchange/binance/archive/fetchers/__init__.py
"""7 个 fetcher 子类，由 factory 装配。"""
from exchange.binance.archive.fetchers.agg_trades import AggTradesFetcher
from exchange.binance.archive.fetchers.trades import TradesFetcher
from exchange.binance.archive.fetchers.book_depth import BookDepthFetcher
from exchange.binance.archive.fetchers.book_ticker import BookTickerFetcher
from exchange.binance.archive.fetchers.mark_price_klines import MarkPriceKlinesFetcher
from exchange.binance.archive.fetchers.index_price_klines import IndexPriceKlinesFetcher
from exchange.binance.archive.fetchers.premium_index_klines import PremiumIndexKlinesFetcher

__all__ = [
    'AggTradesFetcher', 'TradesFetcher', 'BookDepthFetcher', 'BookTickerFetcher',
    'MarkPriceKlinesFetcher', 'IndexPriceKlinesFetcher', 'PremiumIndexKlinesFetcher',
]
```

```python
# backend/exchange/binance/archive/fetchers/agg_trades.py
"""Task 5 完整实现。本 task 提供最小桩。"""
from exchange.binance.archive.kinds import ArchiveKind
from exchange.binance.archive.base import BaseBinanceArchiveDownloader


class AggTradesFetcher(BaseBinanceArchiveDownloader):
    archive_kind = ArchiveKind.AGG_TRADES
    url_subpath = 'aggTrades'
    column_mapping = {
        'agg_trade_id': 'agg_trade_id', 'price': 'price', 'quantity': 'quantity',
        'first_trade_id': 'first_trade_id', 'last_trade_id': 'last_trade_id',
        'transact_time': 'transact_time', 'is_buyer_maker': 'is_buyer_maker',
    }
    parquet_schema = None
```

```python
# backend/exchange/binance/archive/fetchers/trades.py
from exchange.binance.archive.kinds import ArchiveKind
from exchange.binance.archive.base import BaseBinanceArchiveDownloader


class TradesFetcher(BaseBinanceArchiveDownloader):
    archive_kind = ArchiveKind.TRADES
    url_subpath = 'trades'
    column_mapping = {
        'id': 'id', 'price': 'price', 'qty': 'qty', 'quote_qty': 'quote_qty',
        'time': 'time', 'is_buyer_maker': 'is_buyer_maker',
    }
    parquet_schema = None
```

```python
# backend/exchange/binance/archive/fetchers/book_depth.py
from exchange.binance.archive.kinds import ArchiveKind
from exchange.binance.archive.base import BaseBinanceArchiveDownloader


class BookDepthFetcher(BaseBinanceArchiveDownloader):
    archive_kind = ArchiveKind.BOOK_DEPTH
    url_subpath = 'bookDepth'
    column_mapping = {}
    parquet_schema = None
```

```python
# backend/exchange/binance/archive/fetchers/book_ticker.py
from exchange.binance.archive.kinds import ArchiveKind
from exchange.binance.archive.base import BaseBinanceArchiveDownloader


class BookTickerFetcher(BaseBinanceArchiveDownloader):
    archive_kind = ArchiveKind.BOOK_TICKER
    url_subpath = 'bookTicker'
    column_mapping = {
        'update_id': 'update_id', 'symbol': 'symbol',
        'best_bid_price': 'best_bid_price', 'best_bid_qty': 'best_bid_qty',
        'best_ask_price': 'best_ask_price', 'best_ask_qty': 'best_ask_qty',
    }
    parquet_schema = None
```

```python
# backend/exchange/binance/archive/fetchers/mark_price_klines.py
from exchange.binance.archive.kinds import ArchiveKind
from exchange.binance.archive.base import BaseBinanceArchiveDownloader


class MarkPriceKlinesFetcher(BaseBinanceArchiveDownloader):
    archive_kind = ArchiveKind.MARK_KLINES
    url_subpath = 'markPriceKlines'
    column_mapping = {
        'open_time': 'open_time', 'open': 'open', 'high': 'high', 'low': 'low',
        'close': 'close', 'volume': 'volume', 'quote_volume': 'quote_volume',
        'count': 'count',
    }
    parquet_schema = None
```

```python
# backend/exchange/binance/archive/fetchers/index_price_klines.py
from exchange.binance.archive.kinds import ArchiveKind
from exchange.binance.archive.base import BaseBinanceArchiveDownloader


class IndexPriceKlinesFetcher(BaseBinanceArchiveDownloader):
    archive_kind = ArchiveKind.INDEX_KLINES
    url_subpath = 'indexPriceKlines'
    column_mapping = {
        'open_time': 'open_time', 'open': 'open', 'high': 'high', 'low': 'low',
        'close': 'close', 'volume': 'volume', 'quote_volume': 'quote_volume',
        'count': 'count', 'index_price': 'index_price',
    }
    parquet_schema = None
```

```python
# backend/exchange/binance/archive/fetchers/premium_index_klines.py
from exchange.binance.archive.kinds import ArchiveKind
from exchange.binance.archive.base import BaseBinanceArchiveDownloader


class PremiumIndexKlinesFetcher(BaseBinanceArchiveDownloader):
    archive_kind = ArchiveKind.PREMIUM_KLINES
    url_subpath = 'premiumIndexKlines'
    column_mapping = {
        'open_time': 'open_time', 'open': 'open', 'high': 'high', 'low': 'low',
        'close': 'close', 'volume': 'volume', 'quote_volume': 'quote_volume',
        'count': 'count', 'premium_index': 'premium_index',
    }
    parquet_schema = None
```

- [ ] **Step 4: 实现工厂**

```python
# backend/exchange/binance/archive/factory.py
"""7 种数据 × 3 个市场的工厂装配。"""
from __future__ import annotations

from exchange.binance.archive.kinds import ArchiveKind, MarketType
from exchange.binance.archive.base import BaseBinanceArchiveDownloader


class BinanceArchiveFactory:
    """根据 kind + market 返回对应 fetcher 实例。"""

    # 7 个 kind 各自对应一个 fetcher 类（market 仅影响 save_dir / URL 前缀）
    _REGISTRY: dict[ArchiveKind, type[BaseBinanceArchiveDownloader]] = {}

    @classmethod
    def _build_registry(cls) -> None:
        if cls._REGISTRY:
            return
        # 延迟 import 避免循环
        from exchange.binance.archive.fetchers import (
            AggTradesFetcher, TradesFetcher, BookDepthFetcher, BookTickerFetcher,
            MarkPriceKlinesFetcher, IndexPriceKlinesFetcher, PremiumIndexKlinesFetcher,
        )
        cls._REGISTRY = {
            ArchiveKind.AGG_TRADES: AggTradesFetcher,
            ArchiveKind.TRADES: TradesFetcher,
            ArchiveKind.BOOK_DEPTH: BookDepthFetcher,
            ArchiveKind.BOOK_TICKER: BookTickerFetcher,
            ArchiveKind.MARK_KLINES: MarkPriceKlinesFetcher,
            ArchiveKind.INDEX_KLINES: IndexPriceKlinesFetcher,
            ArchiveKind.PREMIUM_KLINES: PremiumIndexKlinesFetcher,
        }

    @classmethod
    def create(
        cls,
        kind: ArchiveKind | str,
        market: MarketType,
        base_dir: str,
        symbol: str,
        interval: str | None = None,
        proxy: str | None = None,
    ) -> BaseBinanceArchiveDownloader:
        cls._build_registry()
        if isinstance(kind, str):
            try:
                kind = ArchiveKind(kind)
            except ValueError as exc:
                raise ValueError(f"Unknown ArchiveKind: {kind!r}") from exc
        fetcher_cls = cls._REGISTRY.get(kind)
        if fetcher_cls is None:
            raise ValueError(f"No fetcher registered for kind: {kind}")
        return fetcher_cls(market=market, base_dir=base_dir, symbol=symbol, interval=interval, proxy=proxy)
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/exchange/binance/archive/test_factory.py -v`
Expected: 5 passed

- [ ] **Step 6: 提交**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add backend/exchange/binance/archive/factory.py backend/exchange/binance/archive/fetchers/ backend/tests/unit/exchange/binance/archive/test_factory.py
git commit -m "feat(archive): BinanceArchiveFactory + 7 fetcher stubs"
```

---

## Task 4: 完整 `_meta.json` 读写（archive_meta.py 升级）

**Files:**
- Modify: `backend/exchange/binance/archive/archive_meta.py`
- Test: `backend/tests/unit/exchange/binance/archive/test_meta.py`

- [ ] **Step 1: 写测试**

```python
# backend/tests/unit/exchange/binance/archive/test_meta.py
import json
from datetime import date
from pathlib import Path
import pyarrow as pa
import pyarrow.parquet as pq
import pandas as pd
from exchange.binance.archive.archive_meta import write_meta, read_meta
from exchange.binance.archive.kinds import ArchiveKind, MarketType


def test_write_meta_creates_file(tmp_path: Path):
    d = tmp_path / 'spot' / 'aggTrades' / 'BTCUSDT'
    d.mkdir(parents=True)
    write_meta(d, 'BTCUSDT', ArchiveKind.AGG_TRADES, MarketType.SPOT, date(2024, 12, 1))
    meta_path = d / '_meta.json'
    assert meta_path.exists()
    data = json.loads(meta_path.read_text())
    assert data['symbol'] == 'BTCUSDT'
    assert data['kind'] == 'aggTrades'
    assert data['market'] == 'spot'
    assert data['earliest_date'] == '2024-12-01'
    assert data['latest_date'] == '2024-12-01'
    assert data['total_rows'] == 0
    assert data['file_count'] == 0


def test_write_meta_updates_existing(tmp_path: Path):
    d = tmp_path / 'spot' / 'aggTrades' / 'BTCUSDT'
    d.mkdir(parents=True)
    write_meta(d, 'BTCUSDT', ArchiveKind.AGG_TRADES, MarketType.SPOT, date(2024, 12, 1))
    write_meta(d, 'BTCUSDT', ArchiveKind.AGG_TRADES, MarketType.SPOT, date(2024, 12, 2))
    data = read_meta(d)
    assert data['earliest_date'] == '2024-12-01'
    assert data['latest_date'] == '2024-12-02'


def test_write_meta_counts_rows_from_parquet(tmp_path: Path):
    d = tmp_path / 'spot' / 'aggTrades' / 'BTCUSDT'
    d.mkdir(parents=True)
    # 写一个含 100 行的 parquet
    df = pd.DataFrame({'price': [1.0] * 100, 'quantity': [0.1] * 100})
    pq.write_table(pa.Table.from_pandas(df), d / 'BTCUSDT-aggTrades-2024-12-01.parquet')
    write_meta(d, 'BTCUSDT', ArchiveKind.AGG_TRADES, MarketType.SPOT, date(2024, 12, 1))
    data = read_meta(d)
    assert data['total_rows'] == 100
    assert data['file_count'] == 1


def test_read_meta_missing_returns_none(tmp_path: Path):
    assert read_meta(tmp_path / 'nonexistent') is None


def test_meta_updated_at_has_nanosecond_precision(tmp_path: Path):
    d = tmp_path / 'spot' / 'aggTrades' / 'BTCUSDT'
    d.mkdir(parents=True)
    write_meta(d, 'BTCUSDT', ArchiveKind.AGG_TRADES, MarketType.SPOT, date(2024, 12, 1))
    data = read_meta(d)
    # 9 位小数 + 时区
    assert '.' in data['updated_at']
    decimals = data['updated_at'].split('.')[1]
    # 去掉时区偏移后的纯数字部分
    digits = ''.join(c for c in decimals if c.isdigit())
    assert len(digits) == 9
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/exchange/binance/archive/test_meta.py -v`
Expected: 测试 4 失败（`write_meta` 当前桩不计数行；`updated_at` 当前精度不对）

- [ ] **Step 3: 完整实现**

```python
# backend/exchange/binance/archive/archive_meta.py
"""_meta.json 读写。

每个 (market, kind, symbol) 目录下一份 _meta.json，结构:
    {
      "symbol": "BTCUSDT",
      "kind": "aggTrades",
      "market": "spot",
      "earliest_date": "2017-08-17",
      "latest_date": "2026-07-15",
      "total_rows": 52345678,
      "file_count": 3207,
      "corrupt_dates": [],
      "updated_at": "2026-07-15T08:00:00.000000000+08:00"
    }
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path

import pyarrow.parquet as pq

from exchange.binance.archive.kinds import ArchiveKind, MarketType

logger = logging.getLogger(__name__)


def _now_iso_ns() -> str:
    """纳秒精度 ISO 8601 时间戳。"""
    return datetime.now().astimezone().isoformat()


def _scan_dir(save_dir: Path) -> tuple[set[date], int]:
    """扫描目录下的 parquet，返回 (所有日期集合, 总行数)。"""
    dates: set[date] = set()
    total_rows = 0
    for p in save_dir.glob('*.parquet'):
        try:
            stem = p.stem
            date_part = stem.split('-')[-3:]
            d = date(int(date_part[0]), int(date_part[1]), int(date_part[2]))
            dates.add(d)
            md = pq.read_metadata(p)
            total_rows += md.num_rows
        except (ValueError, IndexError, Exception) as exc:
            logger.warning("Skip meta scan for %s: %s", p.name, exc)
    return dates, total_rows


def write_meta(
    save_dir: Path,
    symbol: str,
    kind: ArchiveKind,
    market: MarketType,
    last_added_day: date,
) -> dict:
    """扫描目录并重写 _meta.json。"""
    save_dir.mkdir(parents=True, exist_ok=True)
    dates, total_rows = _scan_dir(save_dir)
    if not dates:
        return {}

    existing = read_meta(save_dir) or {}
    corrupt = existing.get('corrupt_dates', [])

    earliest = min(dates).isoformat()
    latest = max(dates).isoformat()
    meta = {
        'symbol': symbol,
        'kind': kind.value,
        'market': market.value,
        'earliest_date': existing.get('earliest_date', earliest),
        'latest_date': max(existing.get('latest_date', '0000-00-00'), latest),
        'total_rows': total_rows,
        'file_count': len(dates),
        'corrupt_dates': corrupt,
        'updated_at': _now_iso_ns(),
    }
    meta_path = save_dir / '_meta.json'
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    return meta


def read_meta(save_dir: Path) -> dict | None:
    """读 _meta.json；不存在返回 None。"""
    meta_path = save_dir / '_meta.json'
    if not meta_path.exists():
        return None
    try:
        return json.loads(meta_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read %s: %s", meta_path, exc)
        return None
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/exchange/binance/archive/test_meta.py -v`
Expected: 5 passed

- [ ] **Step 5: 提交**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add backend/exchange/binance/archive/archive_meta.py backend/tests/unit/exchange/binance/archive/test_meta.py
git commit -m "feat(archive): complete _meta.json with row count + nanosecond timestamp"
```

---

## Task 5: `AggTradesFetcher` 完整实现（端到端跑通的样本）

**Files:**
- Modify: `backend/exchange/binance/archive/fetchers/agg_trades.py`
- Create: `backend/tests/fixtures/archive_zip/BTCUSDT-aggTrades-2024-12-01.zip`（录制）
- Test: `backend/tests/unit/exchange/binance/archive/test_fetchers/test_agg_trades.py`

**目标:** 完成 spec §3.2 中 aggTrades 的 Parquet schema（带类型注解），用 fixture 验证列名映射与 Parquet 写入读回。

- [ ] **Step 1: 录制 fixture**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
mkdir -p backend/tests/fixtures/archive_zip
# 用 curl 拉取真实 BTCUSDT aggTrades 2024-12-01 的小样本（首 1000 条）
curl -L -o backend/tests/fixtures/archive_zip/BTCUSDT-aggTrades-2024-12-01.zip \
  'https://data.binance.vision/data/spot/daily/aggTrades/BTCUSDT/BTCUSDT-aggTrades-2024-12-01.zip'
ls -la backend/tests/fixtures/archive_zip/BTCUSDT-aggTrades-2024-12-01.zip
```

> **如果网络不通**：手动下载放同路径，commit 时作为 binary fixture 入库。

- [ ] **Step 2: 写测试**

```python
# backend/tests/unit/exchange/binance/archive/test_fetchers/test_agg_trades.py
import io
import zipfile
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from exchange.binance.archive.kinds import ArchiveKind, MarketType
from exchange.binance.archive.fetchers.agg_trades import AggTradesFetcher


FIXTURE_DIR = Path(__file__).parents[4] / 'fixtures' / 'archive_zip'


def test_parquet_schema_defines_correct_types():
    f = AggTradesFetcher(market=MarketType.SPOT, base_dir='/tmp', symbol='BTCUSDT')
    schema = f.parquet_schema
    assert schema is not None
    field_names = [f.name for f in schema]
    assert 'agg_trade_id' in field_names
    assert 'price' in field_names
    assert 'quantity' in field_names
    assert 'is_buyer_maker' in field_names
    # 类型检查
    types = {f.name: str(f.type) for f in schema}
    assert 'int64' in types['agg_trade_id']
    assert 'double' in types['price']


def test_transform_df_passes_through_columns():
    f = AggTradesFetcher(market=MarketType.SPOT, base_dir='/tmp', symbol='BTCUSDT')
    raw = pd.DataFrame({
        'agg_trade_id': [1, 2], 'price': [100.0, 101.0], 'quantity': [0.1, 0.2],
        'first_trade_id': [10, 20], 'last_trade_id': [10, 20],
        'transact_time': [1700000000000, 1700000000001], 'is_buyer_maker': [False, True],
    })
    out = f.transform_df(raw)
    assert len(out) == 2
    assert list(out.columns) == list(raw.columns)


def test_save_and_read_round_trip(tmp_path):
    f = AggTradesFetcher(market=MarketType.SPOT, base_dir=tmp_path, symbol='BTCUSDT')
    df = pd.DataFrame({
        'agg_trade_id': pd.array([1, 2, 3], dtype='int64'),
        'price': pd.array([100.0, 101.0, 102.0], dtype='float64'),
        'quantity': pd.array([0.1, 0.2, 0.3], dtype='float64'),
        'first_trade_id': pd.array([10, 20, 30], dtype='int64'),
        'last_trade_id': pd.array([10, 20, 30], dtype='int64'),
        'transact_time': pd.array([1700000000000, 1700000000001, 1700000000002], dtype='int64'),
        'is_buyer_maker': pd.array([False, True, False]),
    })
    f.save_dir.mkdir(parents=True, exist_ok=True)
    from datetime import date
    p = f.save_instrument('BTCUSDT', date(2024, 12, 1), df)
    assert p is not None
    assert p.exists()
    loaded = pd.read_parquet(p)
    assert len(loaded) == 3
    assert loaded['agg_trade_id'].iloc[0] == 1
```

- [ ] **Step 3: 跑测试确认失败**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/exchange/binance/archive/test_fetchers/test_agg_trades.py -v`
Expected: 测试 1 失败（`parquet_schema` 为 None）

- [ ] **Step 4: 完整实现**

```python
# backend/exchange/binance/archive/fetchers/agg_trades.py
"""aggTrades fetcher — 归集逐笔成交。"""
from __future__ import annotations

import pandas as pd
import pyarrow as pa

from exchange.binance.archive.kinds import ArchiveKind
from exchange.binance.archive.base import BaseBinanceArchiveDownloader


AGG_TRADES_SCHEMA = pa.schema([
    pa.field('agg_trade_id', pa.int64()),
    pa.field('price', pa.float64()),
    pa.field('quantity', pa.float64()),
    pa.field('first_trade_id', pa.int64()),
    pa.field('last_trade_id', pa.int64()),
    pa.field('transact_time', pa.int64()),  # 毫秒
    pa.field('is_buyer_maker', pa.bool_()),
])


class AggTradesFetcher(BaseBinanceArchiveDownloader):
    archive_kind = ArchiveKind.AGG_TRADES
    url_subpath = 'aggTrades'
    column_mapping = {
        'agg_trade_id': 'agg_trade_id', 'price': 'price', 'quantity': 'quantity',
        'first_trade_id': 'first_trade_id', 'last_trade_id': 'last_trade_id',
        'transact_time': 'transact_time', 'is_buyer_maker': 'is_buyer_maker',
    }
    parquet_schema = AGG_TRADES_SCHEMA

    def transform_df(self, raw_df: pd.DataFrame) -> pd.DataFrame:
        """aggTrades zip 内的 CSV 带 header，列名已经是 snake_case。"""
        # 强制类型，避免 pandas 推断为 object
        return raw_df.assign(
            agg_trade_id=raw_df['agg_trade_id'].astype('int64'),
            first_trade_id=raw_df['first_trade_id'].astype('int64'),
            last_trade_id=raw_df['last_trade_id'].astype('int64'),
            transact_time=raw_df['transact_time'].astype('int64'),
        )
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/exchange/binance/archive/test_fetchers/test_agg_trades.py -v`
Expected: 3 passed

- [ ] **Step 6: 提交**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add backend/exchange/binance/archive/fetchers/agg_trades.py backend/tests/fixtures/archive_zip/BTCUSDT-aggTrades-2024-12-01.zip backend/tests/unit/exchange/binance/archive/test_fetchers/test_agg_trades.py
git commit -m "feat(archive): AggTradesFetcher with explicit pyarrow schema"
```

---

## Task 6: `TradesFetcher`

**Files:**
- Modify: `backend/exchange/binance/archive/fetchers/trades.py`
- Test: `backend/tests/unit/exchange/binance/archive/test_fetchers/test_trades.py`

- [ ] **Step 1: 写测试**

```python
# backend/tests/unit/exchange/binance/archive/test_fetchers/test_trades.py
import pandas as pd
import pyarrow as pa
from datetime import date
from pathlib import Path
from exchange.binance.archive.kinds import ArchiveKind, MarketType
from exchange.binance.archive.fetchers.trades import TradesFetcher


def test_parquet_schema_defines_correct_types():
    f = TradesFetcher(market=MarketType.SPOT, base_dir='/tmp', symbol='BTCUSDT')
    schema = f.parquet_schema
    field_names = [f.name for f in schema]
    for col in ('id', 'price', 'qty', 'quote_qty', 'time', 'is_buyer_maker'):
        assert col in field_names
    types = {f.name: str(f.type) for f in schema}
    assert 'int64' in types['id']
    assert 'double' in types['price']


def test_trades_zip_has_no_header(tmp_path):
    """Trades zip 内 CSV 不带 header；子类需要重写 _parse_csv_bytes。"""
    f = TradesFetcher(market=MarketType.SPOT, base_dir=tmp_path, symbol='BTCUSDT')
    # 构造一个无 header 的 CSV
    raw_bytes = b'123,100.0,0.1,10.0,1700000000000,false\n124,101.0,0.2,20.2,1700000000001,true\n'
    df = f._parse_csv_bytes(raw_bytes)
    assert len(df) == 2
    assert df.columns[0] == 'id'


def test_save_and_read_round_trip(tmp_path):
    f = TradesFetcher(market=MarketType.SPOT, base_dir=tmp_path, symbol='BTCUSDT')
    f.save_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame({
        'id': pd.array([1, 2], dtype='int64'),
        'price': pd.array([100.0, 101.0], dtype='float64'),
        'qty': pd.array([0.1, 0.2], dtype='float64'),
        'quote_qty': pd.array([10.0, 20.2], dtype='float64'),
        'time': pd.array([1700000000000, 1700000000001], dtype='int64'),
        'is_buyer_maker': pd.array([False, True]),
    })
    p = f.save_instrument('BTCUSDT', date(2024, 12, 1), df)
    loaded = pd.read_parquet(p)
    assert len(loaded) == 2
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/exchange/binance/archive/test_fetchers/test_trades.py -v`
Expected: 测试 1 失败（`parquet_schema` 为 None）

- [ ] **Step 3: 完整实现**

```python
# backend/exchange/binance/archive/fetchers/trades.py
"""Trades fetcher — 原始逐笔成交（zip 内无 header）。"""
from __future__ import annotations

import io
import pandas as pd
import pyarrow as pa

from exchange.binance.archive.kinds import ArchiveKind
from exchange.binance.archive.base import BaseBinanceArchiveDownloader


TRADES_SCHEMA = pa.schema([
    pa.field('id', pa.int64()),
    pa.field('price', pa.float64()),
    pa.field('qty', pa.float64()),
    pa.field('quote_qty', pa.float64()),
    pa.field('time', pa.int64()),
    pa.field('is_buyer_maker', pa.bool_()),
])

# Binance trades zip 内的 CSV 列顺序（无 header）
_TRADES_COLS = ['id', 'price', 'qty', 'quote_qty', 'time', 'is_buyer_maker']


class TradesFetcher(BaseBinanceArchiveDownloader):
    archive_kind = ArchiveKind.TRADES
    url_subpath = 'trades'
    column_mapping = {
        'id': 'id', 'price': 'price', 'qty': 'qty', 'quote_qty': 'quote_qty',
        'time': 'time', 'is_buyer_maker': 'is_buyer_maker',
    }
    parquet_schema = TRADES_SCHEMA

    def _parse_csv_bytes(self, data: bytes) -> pd.DataFrame:
        """Trades zip 内的 CSV 无 header，强制指定列名。"""
        return pd.read_csv(io.BytesIO(data), header=None, names=_TRADES_COLS)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/exchange/binance/archive/test_fetchers/test_trades.py -v`
Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add backend/exchange/binance/archive/fetchers/trades.py backend/tests/unit/exchange/binance/archive/test_fetchers/test_trades.py
git commit -m "feat(archive): TradesFetcher with headerless CSV support"
```

---

## Task 7: `BookTickerFetcher`

**Files:**
- Modify: `backend/exchange/binance/archive/fetchers/book_ticker.py`
- Test: `backend/tests/unit/exchange/binance/archive/test_fetchers/test_book_ticker.py`

- [ ] **Step 1: 写测试**

```python
# backend/tests/unit/exchange/binance/archive/test_fetchers/test_book_ticker.py
import pandas as pd
from datetime import date
from exchange.binance.archive.kinds import ArchiveKind, MarketType
from exchange.binance.archive.fetchers.book_ticker import BookTickerFetcher


def test_schema_has_update_id_and_bid_ask():
    f = BookTickerFetcher(market=MarketType.SPOT, base_dir='/tmp', symbol='BTCUSDT')
    field_names = [f_.name for f_ in f.parquet_schema]
    for col in ('update_id', 'timestamp', 'symbol',
                'best_bid_price', 'best_bid_qty', 'best_ask_price', 'best_ask_qty'):
        assert col in field_names


def test_transform_df_injects_timestamp():
    """bookTicker zip 内单条/日，无时间戳列；按文件日期 + 一天内推。"""
    f = BookTickerFetcher(market=MarketType.SPOT, base_dir='/tmp', symbol='BTCUSDT')
    raw = pd.DataFrame({
        'update_id': [1, 2], 'symbol': ['BTCUSDT', 'BTCUSDT'],
        'best_bid_price': [100.0, 101.0], 'best_bid_qty': [1.0, 2.0],
        'best_ask_price': [101.0, 102.0], 'best_ask_qty': [1.5, 2.5],
    })
    out = f.transform_df(raw)
    assert 'timestamp' in out.columns
    # 实际值会在子类中按调用方提供的 day 注入；此处只验证列存在
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/exchange/binance/archive/test_fetchers/test_book_ticker.py -v`
Expected: 测试 1 失败

- [ ] **Step 3: 完整实现**

```python
# backend/exchange/binance/archive/fetchers/book_ticker.py
"""BookTicker fetcher — 盘口最优价（zip 内单条/日，无时间戳）。"""
from __future__ import annotations

import pandas as pd
import pyarrow as pa

from exchange.binance.archive.kinds import ArchiveKind
from exchange.binance.archive.base import BaseBinanceArchiveDownloader


BOOK_TICKER_SCHEMA = pa.schema([
    pa.field('update_id', pa.int64()),
    pa.field('timestamp', pa.int64()),  # 由 transform_df 注入（毫秒）
    pa.field('symbol', pa.string()),
    pa.field('best_bid_price', pa.float64()),
    pa.field('best_bid_qty', pa.float64()),
    pa.field('best_ask_price', pa.float64()),
    pa.field('best_ask_qty', pa.float64()),
])


class BookTickerFetcher(BaseBinanceArchiveDownloader):
    archive_kind = ArchiveKind.BOOK_TICKER
    url_subpath = 'bookTicker'
    column_mapping = {
        'update_id': 'update_id', 'symbol': 'symbol',
        'best_bid_price': 'best_bid_price', 'best_bid_qty': 'best_bid_qty',
        'best_ask_price': 'best_ask_price', 'best_ask_qty': 'best_ask_qty',
    }
    parquet_schema = BOOK_TICKER_SCHEMA

    def transform_df(self, raw_df: pd.DataFrame) -> pd.DataFrame:
        """bookTicker zip 内没有时间戳；按 save_instrument 调用方提供的 day 注入。"""
        # 由 save_instrument 单独写入时间戳；这里先返回原 df（无 timestamp 列）
        return raw_df

    def save_instrument(self, symbol: str, day, df: pd.DataFrame):
        """重写以注入 timestamp（unix 毫秒 = 当天 00:00 UTC）。"""
        if df.empty:
            return None
        self.save_dir.mkdir(parents=True, exist_ok=True)
        ts_ms = int(day.strftime('%s')) * 1000
        if 'timestamp' not in df.columns:
            df = df.copy()
            df['timestamp'] = ts_ms
        # 重排列顺序对齐 schema
        ordered_cols = [f.name for f in BOOK_TICKER_SCHEMA]
        for c in ordered_cols:
            if c not in df.columns:
                df[c] = None
        df = df[ordered_cols]
        from exchange.binance.archive.fetchers.book_ticker import BOOK_TICKER_SCHEMA  # noqa
        import pyarrow as pa
        table = pa.Table.from_pandas(df, schema=BOOK_TICKER_SCHEMA, preserve_index=False)
        out_path = self.save_dir / f'{symbol}-{self.archive_kind.value}-{day.isoformat()}.parquet'
        import pyarrow.parquet as pq
        pq.write_table(table, out_path, compression='snappy')
        return out_path
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/exchange/binance/archive/test_fetchers/test_book_ticker.py -v`
Expected: 2 passed

- [ ] **Step 5: 提交**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add backend/exchange/binance/archive/fetchers/book_ticker.py backend/tests/unit/exchange/binance/archive/test_fetchers/test_book_ticker.py
git commit -m "feat(archive): BookTickerFetcher with timestamp injection"
```

---

## Task 8: `BookDepthFetcher`（嵌套 bids/asks 展平）

**Files:**
- Modify: `backend/exchange/binance/archive/fetchers/book_depth.py`
- Test: `backend/tests/unit/exchange/binance/archive/test_fetchers/test_book_depth.py`

- [ ] **Step 1: 写测试**

```python
# backend/tests/unit/exchange/binance/archive/test_fetchers/test_book_depth.py
import pandas as pd
from exchange.binance.archive.kinds import ArchiveKind, MarketType
from exchange.binance.archive.fetchers.book_depth import BookDepthFetcher


def test_schema_has_long_format_columns():
    f = BookDepthFetcher(market=MarketType.SPOT, base_dir='/tmp', symbol='BTCUSDT')
    field_names = [f_.name for f_ in f.parquet_schema]
    for col in ('timestamp', 'symbol', 'side', 'level', 'price', 'quantity'):
        assert col in field_names


def test_transform_df_unrolls_bids_asks():
    """bookDepth zip 内的 CSV 每行有 bids[20] + asks[20] 嵌套数组，需要展平。"""
    f = BookDepthFetcher(market=MarketType.SPOT, base_dir='/tmp', symbol='BTCUSDT')
    # 模拟 1 条记录：bids/asks 均为 [[price, qty], ...]
    raw = pd.DataFrame({
        'timestamp': [1700000000000],
        'symbol': ['BTCUSDT'],
        'bids': [[['100.0', '1.0'], ['99.0', '2.0']]],
        'asks': [[['101.0', '1.5'], ['102.0', '2.5']]],
    })
    out = f.transform_df(raw)
    # 1 条记录 → bids 2 行 + asks 2 行 = 4 行
    assert len(out) == 4
    # 必有 side 列
    assert 'side' in out.columns
    # 必有 level 列（0=最优）
    assert 'level' in out.columns
    # bids 2 条
    assert (out['side'] == 'bid').sum() == 2
    # asks 2 条
    assert (out['side'] == 'ask').sum() == 2
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/exchange/binance/archive/test_fetchers/test_book_depth.py -v`
Expected: 测试 1 失败

- [ ] **Step 3: 完整实现**

```python
# backend/exchange/binance/archive/fetchers/book_depth.py
"""BookDepth fetcher — 部分订单簿深度（嵌套 bids/asks 展平为长表）。"""
from __future__ import annotations

import pandas as pd
import pyarrow as pa

from exchange.binance.archive.kinds import ArchiveKind
from exchange.binance.archive.base import BaseBinanceArchiveDownloader


BOOK_DEPTH_SCHEMA = pa.schema([
    pa.field('timestamp', pa.int64()),
    pa.field('symbol', pa.string()),
    pa.field('side', pa.string()),  # 'bid' / 'ask'
    pa.field('level', pa.int32()),
    pa.field('price', pa.float64()),
    pa.field('quantity', pa.float64()),
])


class BookDepthFetcher(BaseBinanceArchiveDownloader):
    archive_kind = ArchiveKind.BOOK_DEPTH
    url_subpath = 'bookDepth'
    column_mapping = {}  # 列名是构造出来的
    parquet_schema = BOOK_DEPTH_SCHEMA

    def _parse_csv_bytes(self, data):
        """bookDepth zip 内的 CSV 有 bids/asks 嵌套数组。"""
        import io
        return pd.read_csv(
            io.BytesIO(data),
            converters={
                'bids': lambda x: eval(x),  # noqa: S307 — 可信数据源
                'asks': lambda x: eval(x),  # noqa: S307
            },
        )

    def transform_df(self, raw_df: pd.DataFrame) -> pd.DataFrame:
        """把 bids[20] + asks[20] 展平成 (side, level, price, quantity) 长表。"""
        rows: list[dict] = []
        for _, r in raw_df.iterrows():
            for level, (price, qty) in enumerate(r['bids']):
                rows.append({
                    'timestamp': r['timestamp'], 'symbol': r['symbol'],
                    'side': 'bid', 'level': level,
                    'price': float(price), 'quantity': float(qty),
                })
            for level, (price, qty) in enumerate(r['asks']):
                rows.append({
                    'timestamp': r['timestamp'], 'symbol': r['symbol'],
                    'side': 'ask', 'level': level,
                    'price': float(price), 'quantity': float(qty),
                })
        return pd.DataFrame(rows, columns=['timestamp', 'symbol', 'side', 'level', 'price', 'quantity'])
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/exchange/binance/archive/test_fetchers/test_book_depth.py -v`
Expected: 2 passed

- [ ] **Step 5: 提交**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add backend/exchange/binance/archive/fetchers/book_depth.py backend/tests/unit/exchange/binance/archive/test_fetchers/test_book_depth.py
git commit -m "feat(archive): BookDepthFetcher with bids/asks nested unrolling"
```

---

## Task 9: `MarkPriceKlinesFetcher`

**Files:**
- Modify: `backend/exchange/binance/archive/fetchers/mark_price_klines.py`
- Test: `backend/tests/unit/exchange/binance/archive/test_fetchers/test_mark_klines.py`

- [ ] **Step 1: 写测试**

```python
# backend/tests/unit/exchange/binance/archive/test_fetchers/test_mark_klines.py
import pandas as pd
from datetime import date
from exchange.binance.archive.kinds import ArchiveKind, MarketType
from exchange.binance.archive.fetchers.mark_price_klines import MarkPriceKlinesFetcher


def test_schema_has_kline_columns():
    f = MarkPriceKlinesFetcher(market=MarketType.FUTURES_UM, base_dir='/tmp', symbol='BTCUSDT', interval='1h')
    field_names = [f_.name for f_ in f.parquet_schema]
    for col in ('open_time', 'open', 'high', 'low', 'close', 'volume', 'quote_volume', 'count'):
        assert col in field_names


def test_interval_appears_in_url(tmp_path):
    f = MarkPriceKlinesFetcher(market=MarketType.FUTURES_UM, base_dir=tmp_path, symbol='BTCUSDT', interval='1h')
    url = f.get_zip_url('BTCUSDT', '2024-12-01')
    assert '/1h/' in url
    assert 'markPriceKlines-1h-' in url


def test_save_and_read_round_trip(tmp_path):
    f = MarkPriceKlinesFetcher(market=MarketType.FUTURES_UM, base_dir=tmp_path, symbol='BTCUSDT', interval='1h')
    f.save_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame({
        'open_time': pd.array([1700000000000, 1700003600000], dtype='int64'),
        'open': pd.array([100.0, 101.0], dtype='float64'),
        'high': pd.array([101.0, 102.0], dtype='float64'),
        'low': pd.array([99.0, 100.0], dtype='float64'),
        'close': pd.array([100.5, 101.5], dtype='float64'),
        'volume': pd.array([10.0, 11.0], dtype='float64'),
        'quote_volume': pd.array([1000.0, 1100.0], dtype='float64'),
        'count': pd.array([100, 110], dtype='int32'),
    })
    p = f.save_instrument('BTCUSDT', date(2024, 12, 1), df)
    loaded = pd.read_parquet(p)
    assert len(loaded) == 2
    assert loaded['open'].iloc[0] == 100.0
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/exchange/binance/archive/test_fetchers/test_mark_klines.py -v`
Expected: 测试 1 失败

- [ ] **Step 3: 完整实现**

```python
# backend/exchange/binance/archive/fetchers/mark_price_klines.py
"""MarkPriceKlines fetcher — 标记价 K 线（合约用）。"""
from __future__ import annotations

import pandas as pd
import pyarrow as pa

from exchange.binance.archive.kinds import ArchiveKind
from exchange.binance.archive.base import BaseBinanceArchiveDownloader


MARK_KLINES_SCHEMA = pa.schema([
    pa.field('open_time', pa.int64()),
    pa.field('open', pa.float64()),
    pa.field('high', pa.float64()),
    pa.field('low', pa.float64()),
    pa.field('close', pa.float64()),
    pa.field('volume', pa.float64()),
    pa.field('quote_volume', pa.float64()),
    pa.field('count', pa.int32()),
])


class MarkPriceKlinesFetcher(BaseBinanceArchiveDownloader):
    archive_kind = ArchiveKind.MARK_KLINES
    url_subpath = 'markPriceKlines'
    column_mapping = {
        'open_time': 'open_time', 'open': 'open', 'high': 'high', 'low': 'low',
        'close': 'close', 'volume': 'volume', 'quote_volume': 'quote_volume',
        'count': 'count',
    }
    parquet_schema = MARK_KLINES_SCHEMA
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/exchange/binance/archive/test_fetchers/test_mark_klines.py -v`
Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add backend/exchange/binance/archive/fetchers/mark_price_klines.py backend/tests/unit/exchange/binance/archive/test_fetchers/test_mark_klines.py
git commit -m "feat(archive): MarkPriceKlinesFetcher"
```

---

## Task 10: `IndexPriceKlinesFetcher`

**Files:**
- Modify: `backend/exchange/binance/archive/fetchers/index_price_klines.py`
- Test: `backend/tests/unit/exchange/binance/archive/test_fetchers/test_index_klines.py`

- [ ] **Step 1: 写测试**

```python
# backend/tests/unit/exchange/binance/archive/test_fetchers/test_index_klines.py
from exchange.binance.archive.kinds import ArchiveKind, MarketType
from exchange.binance.archive.fetchers.index_price_klines import IndexPriceKlinesFetcher


def test_schema_has_index_price_column():
    f = IndexPriceKlinesFetcher(market=MarketType.FUTURES_UM, base_dir='/tmp', symbol='BTCUSDT', interval='1h')
    field_names = [f_.name for f_ in f.parquet_schema]
    for col in ('open_time', 'open', 'high', 'low', 'close', 'volume', 'quote_volume', 'count', 'index_price'):
        assert col in field_names
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/exchange/binance/archive/test_fetchers/test_index_klines.py -v`
Expected: 失败

- [ ] **Step 3: 完整实现**

```python
# backend/exchange/binance/archive/fetchers/index_price_klines.py
"""IndexPriceKlines fetcher — 指数价 K 线。"""
from __future__ import annotations

import pyarrow as pa

from exchange.binance.archive.kinds import ArchiveKind
from exchange.binance.archive.base import BaseBinanceArchiveDownloader


INDEX_KLINES_SCHEMA = pa.schema([
    pa.field('open_time', pa.int64()),
    pa.field('open', pa.float64()),
    pa.field('high', pa.float64()),
    pa.field('low', pa.float64()),
    pa.field('close', pa.float64()),
    pa.field('volume', pa.float64()),
    pa.field('quote_volume', pa.float64()),
    pa.field('count', pa.int32()),
    pa.field('index_price', pa.float64()),
])


class IndexPriceKlinesFetcher(BaseBinanceArchiveDownloader):
    archive_kind = ArchiveKind.INDEX_KLINES
    url_subpath = 'indexPriceKlines'
    column_mapping = {
        'open_time': 'open_time', 'open': 'open', 'high': 'high', 'low': 'low',
        'close': 'close', 'volume': 'volume', 'quote_volume': 'quote_volume',
        'count': 'count', 'index_price': 'index_price',
    }
    parquet_schema = INDEX_KLINES_SCHEMA
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/exchange/binance/archive/test_fetchers/test_index_klines.py -v`
Expected: 1 passed

- [ ] **Step 5: 提交**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add backend/exchange/binance/archive/fetchers/index_price_klines.py backend/tests/unit/exchange/binance/archive/test_fetchers/test_index_klines.py
git commit -m "feat(archive): IndexPriceKlinesFetcher"
```

---

## Task 11: `PremiumIndexKlinesFetcher`

**Files:**
- Modify: `backend/exchange/binance/archive/fetchers/premium_index_klines.py`
- Test: `backend/tests/unit/exchange/binance/archive/test_fetchers/test_premium_klines.py`

- [ ] **Step 1: 写测试**

```python
# backend/tests/unit/exchange/binance/archive/test_fetchers/test_premium_klines.py
from exchange.binance.archive.kinds import ArchiveKind, MarketType
from exchange.binance.archive.fetchers.premium_index_klines import PremiumIndexKlinesFetcher


def test_schema_has_premium_index_column():
    f = PremiumIndexKlinesFetcher(market=MarketType.FUTURES_UM, base_dir='/tmp', symbol='BTCUSDT', interval='1h')
    field_names = [f_.name for f_ in f.parquet_schema]
    for col in ('open_time', 'open', 'high', 'low', 'close', 'volume', 'quote_volume', 'count', 'premium_index'):
        assert col in field_names
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/exchange/binance/archive/test_fetchers/test_premium_klines.py -v`
Expected: 失败

- [ ] **Step 3: 完整实现**

```python
# backend/exchange/binance/archive/fetchers/premium_index_klines.py
"""PremiumIndexKlines fetcher — 溢价指数 K 线。"""
from __future__ import annotations

import pyarrow as pa

from exchange.binance.archive.kinds import ArchiveKind
from exchange.binance.archive.base import BaseBinanceArchiveDownloader


PREMIUM_KLINES_SCHEMA = pa.schema([
    pa.field('open_time', pa.int64()),
    pa.field('open', pa.float64()),
    pa.field('high', pa.float64()),
    pa.field('low', pa.float64()),
    pa.field('close', pa.float64()),
    pa.field('volume', pa.float64()),
    pa.field('quote_volume', pa.float64()),
    pa.field('count', pa.int32()),
    pa.field('premium_index', pa.float64()),
])


class PremiumIndexKlinesFetcher(BaseBinanceArchiveDownloader):
    archive_kind = ArchiveKind.PREMIUM_KLINES
    url_subpath = 'premiumIndexKlines'
    column_mapping = {
        'open_time': 'open_time', 'open': 'open', 'high': 'high', 'low': 'low',
        'close': 'close', 'volume': 'volume', 'quote_volume': 'quote_volume',
        'count': 'count', 'premium_index': 'premium_index',
    }
    parquet_schema = PREMIUM_KLINES_SCHEMA
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/exchange/binance/archive/test_fetchers/test_premium_klines.py -v`
Expected: 1 passed

- [ ] **Step 5: 提交**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add backend/exchange/binance/archive/fetchers/premium_index_klines.py backend/tests/unit/exchange/binance/archive/test_fetchers/test_premium_klines.py
git commit -m "feat(archive): PremiumIndexKlinesFetcher"
```

---

## Task 12: 业务编排层 `archive_service.py`

**Files:**
- Create: `backend/collector/services/archive_service.py`
- Test: `backend/tests/unit/collector/services/test_archive_service.py`

- [ ] **Step 1: 写测试**

```python
# backend/tests/unit/collector/services/test_archive_service.py
from unittest.mock import MagicMock, patch
from exchange.binance.archive.kinds import ArchiveKind, MarketType
from collector.services.archive_service import ArchiveService


def test_create_download_task_uses_task_manager():
    svc = ArchiveService(base_dir='/tmp', proxy='http://proxy:8080')
    with patch('collector.services.archive_service.task_manager') as mock_tm:
        mock_tm.create_task.return_value = 'task-123'
        task_id = svc.create_download_task(
            symbols=['BTCUSDT'], kind=ArchiveKind.AGG_TRADES, market=MarketType.SPOT,
            start_date='2024-12-01', end_date='2024-12-02', mode='inc',
        )
    assert task_id == 'task-123'
    mock_tm.create_task.assert_called_once()
    kwargs = mock_tm.create_task.call_args.kwargs
    assert kwargs['task_type'] == 'archive_agg_trades'
    assert kwargs['params']['symbols'] == ['BTCUSDT']


def test_create_download_task_dispatches_correct_kind():
    svc = ArchiveService(base_dir='/tmp')
    with patch('collector.services.archive_service.task_manager') as mock_tm:
        svc.create_download_task(
            symbols=['BTCUSDT'], kind=ArchiveKind.MARK_KLINES, market=MarketType.FUTURES_UM,
            start_date='2024-12-01', end_date='2024-12-02', mode='inc', interval='1h',
        )
    kwargs = mock_tm.create_task.call_args.kwargs
    assert kwargs['task_type'] == 'archive_mark_klines'
    assert kwargs['params']['interval'] == '1h'


def test_get_meta_returns_dict():
    svc = ArchiveService(base_dir='/tmp')
    with patch('exchange.binance.archive.archive_meta.read_meta') as mock_read:
        mock_read.return_value = {'symbol': 'BTCUSDT', 'kind': 'aggTrades'}
        meta = svc.get_meta(ArchiveKind.AGG_TRADES, MarketType.SPOT, 'BTCUSDT')
    assert meta['symbol'] == 'BTCUSDT'
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/collector/services/test_archive_service.py -v`
Expected: `ModuleNotFoundError`

- [ ] **Step 3: 实现**

```python
# backend/collector/services/archive_service.py
"""归档数据业务编排层。

薄编排层，不做实际下载逻辑。所有下载走 fetcher；
任务调度走现有 task_manager；元数据走 archive_meta。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

from collector.task_manager import task_manager
from exchange.binance.archive.archive_meta import read_meta
from exchange.binance.archive.factory import BinanceArchiveFactory
from exchange.binance.archive.kinds import (
    ArchiveKind,
    MarketType,
    get_save_dir,
    KIND_INTERVALS,
)

logger = logging.getLogger(__name__)

# 7 个 kind → task_type 枚举
KIND_TASK_TYPE: dict[ArchiveKind, str] = {
    ArchiveKind.AGG_TRADES: 'archive_agg_trades',
    ArchiveKind.TRADES: 'archive_trades',
    ArchiveKind.BOOK_DEPTH: 'archive_book_depth',
    ArchiveKind.BOOK_TICKER: 'archive_book_ticker',
    ArchiveKind.MARK_KLINES: 'archive_mark_klines',
    ArchiveKind.INDEX_KLINES: 'archive_index_klines',
    ArchiveKind.PREMIUM_KLINES: 'archive_premium_klines',
}


class ArchiveService:
    def __init__(self, base_dir: str | Path, proxy: str | None = None) -> None:
        self.base_dir = Path(base_dir)
        self.proxy = proxy

    def create_download_task(
        self,
        symbols: list[str],
        kind: ArchiveKind,
        market: MarketType,
        start_date: str,
        end_date: str,
        mode: Literal['inc', 'full'] = 'inc',
        interval: str | None = None,
    ) -> str:
        # K 线类必须传 interval
        allowed_intervals = KIND_INTERVALS[kind]
        if allowed_intervals is not None and interval not in allowed_intervals:
            raise ValueError(
                f"kind={kind.value} requires interval in {allowed_intervals}, got {interval!r}"
            )

        task_type = KIND_TASK_TYPE[kind]
        task_id = task_manager.create_task(
            task_type=task_type,
            params={
                'symbols': symbols, 'market': market.value,
                'start_date': start_date, 'end_date': end_date,
                'mode': mode, 'interval': interval,
            },
        )
        logger.info("Created %s task %s for %s", task_type, task_id, symbols)
        return task_id

    def query_data(
        self, kind: ArchiveKind, market: MarketType, symbol: str,
        start_time: int, end_time: int, limit: int = 1000, offset: int = 0,
    ) -> dict:
        fetcher = BinanceArchiveFactory.create(
            kind, market, base_dir=str(self.base_dir), symbol=symbol,
            interval=None, proxy=self.proxy,
        )
        return fetcher.read_range(symbol, start_time, end_time, limit, offset)

    def get_meta(self, kind: ArchiveKind, market: MarketType, symbol: str) -> dict | None:
        save_dir = get_save_dir(self.base_dir, market, kind, symbol)
        return read_meta(save_dir)

    def list_symbols(self, kind: ArchiveKind, market: MarketType) -> list[str]:
        """列出某 (kind, market) 下已采集的 symbols。"""
        base = self.base_dir / market.value / kind.value
        if not base.exists():
            return []
        return sorted([p.name for p in base.iterdir() if p.is_dir()])
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/collector/services/test_archive_service.py -v`
Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add backend/collector/services/archive_service.py backend/tests/unit/collector/services/test_archive_service.py
git commit -m "feat(archive): ArchiveService business orchestration"
```

---

## Task 13: REST API（6 个端点）

**Files:**
- Create: `backend/collector/api/archive.py`
- Modify: `backend/collector/api/__init__.py`（注册 router）
- Test: `backend/tests/integration/test_archive_api.py`

- [ ] **Step 1: 写测试**

```python
# backend/tests/integration/test_archive_api.py
import pytest
from fastapi.testclient import TestClient
from main import app
from exchange.binance.archive.kinds import ArchiveKind, MarketType


@pytest.fixture
def client():
    return TestClient(app)


def test_post_archive_download_returns_task_id(client, monkeypatch):
    # mock ArchiveService.create_download_task
    from collector.services import archive_service
    monkeypatch.setattr(archive_service.ArchiveService, 'create_download_task', lambda self, **kw: 'task-xyz')

    resp = client.post('/api/data/archive/download', json={
        'symbols': ['BTCUSDT'], 'kind': 'aggTrades', 'market': 'spot',
        'start_date': '2024-12-01', 'end_date': '2024-12-02', 'mode': 'inc',
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data['task_id'] == 'task-xyz'


def test_get_archive_symbols_returns_list(client, monkeypatch):
    from collector.services import archive_service
    monkeypatch.setattr(archive_service.ArchiveService, 'list_symbols', lambda self, k, m: ['BTCUSDT', 'ETHUSDT'])

    resp = client.get('/api/data/archive/symbols?kind=aggTrades&market=spot')
    assert resp.status_code == 200
    data = resp.json()
    assert 'BTCUSDT' in data['symbols']


def test_get_archive_data_returns_paginated_rows(client, monkeypatch):
    from collector.services import archive_service
    monkeypatch.setattr(archive_service.ArchiveService, 'query_data',
                        lambda self, k, m, s, st, et, l, o: {'total': 1000, 'rows': [{'price': 100}], 'truncated': False})

    resp = client.get('/api/data/archive/data?kind=aggTrades&market=spot&symbol=BTCUSDT&start_time=0&end_time=99999999999999')
    assert resp.status_code == 200
    data = resp.json()
    assert data['total'] == 1000


def test_post_archive_download_invalid_kind_returns_400(client):
    resp = client.post('/api/data/archive/download', json={
        'symbols': ['BTCUSDT'], 'kind': 'not_a_kind', 'market': 'spot',
        'start_date': '2024-12-01', 'end_date': '2024-12-02',
    })
    assert resp.status_code in (400, 422)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_archive_api.py -v`
Expected: 失败（路由不存在）

- [ ] **Step 3: 实现 router**

```python
# backend/collector/api/archive.py
"""归档数据 REST API（6 个端点）。"""
from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from collector.services.archive_service import ArchiveService
from exchange.binance.archive.kinds import ArchiveKind, MarketType

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/api/data/archive', tags=['archive'])


def _get_service() -> ArchiveService:
    """从 settings / system_config 解析 base_dir + proxy。"""
    from collector.config import get_archive_base_dir, get_binance_proxy
    return ArchiveService(base_dir=get_archive_base_dir(), proxy=get_binance_proxy())


# —— 1) POST /archive/download ——
class DownloadRequest(BaseModel):
    symbols: list[str] = Field(..., min_length=1)
    kind: str
    market: str
    start_date: str
    end_date: str
    mode: Literal['inc', 'full'] = 'inc'
    interval: str | None = None


@router.post('/download')
def post_download(req: DownloadRequest) -> dict:
    try:
        kind = ArchiveKind(req.kind)
        market = MarketType(req.market)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    svc = _get_service()
    try:
        task_id = svc.create_download_task(
            symbols=req.symbols, kind=kind, market=market,
            start_date=req.start_date, end_date=req.end_date,
            mode=req.mode, interval=req.interval,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {'success': True, 'task_id': task_id}


# —— 2) GET /archive/tasks/{task_id} ——
@router.get('/tasks/{task_id}')
def get_task_progress(task_id: str) -> dict:
    from collector.task_manager import task_manager
    status = task_manager.get_task_status(task_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f'task {task_id} not found')
    return status


# —— 3) GET /archive/symbols ——
@router.get('/symbols')
def get_symbols(kind: str = Query(...), market: str = Query(...)) -> dict:
    try:
        kind_e = ArchiveKind(kind)
        market_e = MarketType(market)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    svc = _get_service()
    return {'success': True, 'symbols': svc.list_symbols(kind_e, market_e)}


# —— 4) GET /archive/data ——
@router.get('/data')
def get_data(
    kind: str = Query(...),
    market: str = Query(...),
    symbol: str = Query(...),
    start_time: int = Query(...),
    end_time: int = Query(...),
    limit: int = Query(1000, ge=1, le=1_000_000),
    offset: int = Query(0, ge=0),
) -> dict:
    try:
        kind_e = ArchiveKind(kind)
        market_e = MarketType(market)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    svc = _get_service()
    return svc.query_data(kind_e, market_e, symbol, start_time, end_time, limit, offset)


# —— 5) GET /archive/meta/{kind}/{market}/{symbol} ——
@router.get('/meta/{kind}/{market}/{symbol}')
def get_meta(kind: str, market: str, symbol: str) -> dict:
    try:
        kind_e = ArchiveKind(kind)
        market_e = MarketType(market)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    svc = _get_service()
    meta = svc.get_meta(kind_e, market_e, symbol)
    if meta is None:
        return {'success': True, 'meta': None}
    return {'success': True, 'meta': meta}


# —— 6) DELETE /archive/data ——
@router.delete('/data')
def delete_data(kind: str = Query(...), market: str = Query(...), symbol: str = Query(...)) -> dict:
    import shutil
    from exchange.binance.archive.kinds import get_save_dir
    try:
        kind_e = ArchiveKind(kind)
        market_e = MarketType(market)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    svc = _get_service()
    save_dir = get_save_dir(svc.base_dir, market_e, kind_e, symbol)
    if save_dir.exists():
        shutil.rmtree(save_dir)
        return {'success': True, 'deleted': str(save_dir)}
    return {'success': True, 'deleted': None}
```

- [ ] **Step 4: 注册 router**

Modify `backend/collector/api/__init__.py`，追加：

```python
from collector.api.archive import router as archive_router
# ...在已有的 include_router 之后追加：
# app.include_router(archive_router)
```

具体拼接方式参考文件内现有的 `kline_router` 注册。

- [ ] **Step 5: 在 `backend/collector/config.py` 加 2 个 helper（不存在则创建）**

```python
# backend/collector/config.py（追加；若文件已有则只追加函数）
from pathlib import Path
from exchange.binance.archive.kinds import MarketType


def get_archive_base_dir() -> Path:
    """返回归档数据存储根目录。可从 system_config 读；这里给默认。"""
    from collector.db.crud import get_system_config
    cfg = get_system_config('data.archive.base_dir')
    if cfg:
        return Path(cfg)
    return Path('/Users/liupeng/workspace/quant/QuantCell/backend/data/source/archive')


def get_binance_proxy() -> str | None:
    from collector.db.crud import get_system_config
    return get_system_config('exchange.binance.proxy') or None
```

- [ ] **Step 6: 跑测试确认通过**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_archive_api.py -v`
Expected: 4 passed

- [ ] **Step 7: 提交**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add backend/collector/api/archive.py backend/collector/api/__init__.py backend/collector/config.py backend/tests/integration/test_archive_api.py
git commit -m "feat(archive): 6 REST endpoints + router registration"
```

---

## Task 14: CLI 子命令

**Files:**
- Modify: `backend/cli/data.py`（追加 archive subcommand）
- Test: `backend/tests/unit/cli/test_data_archive.py`

- [ ] **Step 1: 写测试**

```python
# backend/tests/unit/cli/test_data_archive.py
from typer.testing import CliRunner
from cli.data import app


runner = CliRunner()


def test_cli_data_archive_help():
    result = runner.invoke(app, ['archive', '--help'])
    assert result.exit_code == 0
    assert 'download' in result.output
    assert 'list' in result.output
    assert 'meta' in result.output


def test_cli_data_archive_download_invokes_service(monkeypatch):
    from collector.services import archive_service
    captured = {}
    monkeypatch.setattr(archive_service.ArchiveService, 'create_download_task',
                        lambda self, **kw: captured.update(kw) or 'task-999')

    result = runner.invoke(app, [
        'archive', 'download',
        '--kind', 'aggTrades', '--market', 'spot',
        '--symbols', 'BTCUSDT,ETHUSDT',
        '--start', '2024-12-01', '--end', '2024-12-02',
        '--mode', 'inc',
    ])
    assert result.exit_code == 0
    assert captured['symbols'] == ['BTCUSDT', 'ETHUSDT']
    assert captured['start_date'] == '2024-12-01'


def test_cli_data_archive_meta(monkeypatch):
    from collector.services import archive_service
    monkeypatch.setattr(archive_service.ArchiveService, 'get_meta',
                        lambda self, k, m, s: {'symbol': s, 'latest_date': '2024-12-02'})

    result = runner.invoke(app, [
        'archive', 'meta', '--kind', 'aggTrades', '--market', 'spot', '--symbol', 'BTCUSDT',
    ])
    assert result.exit_code == 0
    assert 'BTCUSDT' in result.output
    assert '2024-12-02' in result.output
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/cli/test_data_archive.py -v`
Expected: 失败

- [ ] **Step 3: 在 `backend/cli/data.py` 追加 archive subcommand**

```python
# backend/cli/data.py（在文件末尾追加；不覆盖现有代码）
import typer
from typing import Optional
from exchange.binance.archive.kinds import ArchiveKind, MarketType
from collector.services.archive_service import ArchiveService
from collector.config import get_archive_base_dir, get_binance_proxy

archive_app = typer.Typer(help="Binance 历史归档数据采集")
app.add_typer(archive_app, name='archive')


@archive_app.command('download')
def archive_download(
    kind: str = typer.Option(..., help='aggTrades / trades / bookDepth / bookTicker / markPriceKlines / indexPriceKlines / premiumIndexKlines'),
    market: str = typer.Option(..., help='spot / um / cm'),
    symbols: str = typer.Option(..., help='逗号分隔，如 BTCUSDT,ETHUSDT'),
    start: str = typer.Option(..., help='起始日期 YYYY-MM-DD'),
    end: str = typer.Option(..., help='结束日期 YYYY-MM-DD'),
    mode: str = typer.Option('inc', help='inc / full'),
    interval: Optional[str] = typer.Option(None, help='仅 K 线类需要：1m/3m/5m/15m/30m/1h/2h/1d'),
):
    svc = ArchiveService(base_dir=get_archive_base_dir(), proxy=get_binance_proxy())
    sym_list = [s.strip() for s in symbols.split(',') if s.strip()]
    task_id = svc.create_download_task(
        symbols=sym_list, kind=ArchiveKind(kind), market=MarketType(market),
        start_date=start, end_date=end, mode=mode, interval=interval,
    )
    typer.echo(f"Task created: {task_id}")


@archive_app.command('list')
def archive_list(
    kind: str = typer.Option(...),
    market: str = typer.Option(...),
):
    svc = ArchiveService(base_dir=get_archive_base_dir(), proxy=get_binance_proxy())
    symbols = svc.list_symbols(ArchiveKind(kind), MarketType(market))
    for s in symbols:
        typer.echo(s)


@archive_app.command('meta')
def archive_meta(
    kind: str = typer.Option(...),
    market: str = typer.Option(...),
    symbol: str = typer.Option(...),
):
    import json
    svc = ArchiveService(base_dir=get_archive_base_dir(), proxy=get_binance_proxy())
    meta = svc.get_meta(ArchiveKind(kind), MarketType(market), symbol)
    if meta is None:
        typer.echo("No meta found")
    else:
        typer.echo(json.dumps(meta, ensure_ascii=False, indent=2))
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/cli/test_data_archive.py -v`
Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add backend/cli/data.py backend/tests/unit/cli/test_data_archive.py
git commit -m "feat(archive): CLI subcommand 'quantcell data archive ...'"
```

---

## Task 15: 前端 API 客户端 + 类型

**Files:**
- Modify: `frontend/src/api/dataApi.ts`
- Modify: `frontend/src/types/data.ts`
- Verify: `cd frontend && bun run build`

- [ ] **Step 1: 在 `frontend/src/types/data.ts` 追加类型**

```typescript
// frontend/src/types/data.ts（追加在文件末尾）

export type ArchiveKind =
  | 'aggTrades'
  | 'trades'
  | 'bookDepth'
  | 'bookTicker'
  | 'markPriceKlines'
  | 'indexPriceKlines'
  | 'premiumIndexKlines';

export type MarketType = 'spot' | 'um' | 'cm';

export const ARCHIVE_KINDS: ArchiveKind[] = [
  'aggTrades', 'trades', 'bookDepth', 'bookTicker',
  'markPriceKlines', 'indexPriceKlines', 'premiumIndexKlines',
];

export const KLINE_ARCHIVE_KINDS: ArchiveKind[] = [
  'markPriceKlines', 'indexPriceKlines', 'premiumIndexKlines',
];

export const ARCHIVE_INTERVALS: string[] = [
  '1m', '3m', '5m', '15m', '30m', '1h', '2h', '1d',
];

export interface ArchiveTaskRequest {
  symbols: string[];
  kind: ArchiveKind;
  market: MarketType;
  start_date: string;
  end_date: string;
  mode: 'inc' | 'full';
  interval?: string;
}

export interface ArchiveRow {
  [key: string]: string | number | boolean | null;
}

export interface ArchiveMeta {
  symbol: string;
  kind: string;
  market: string;
  earliest_date: string;
  latest_date: string;
  total_rows: number;
  file_count: number;
  corrupt_dates: string[];
  updated_at: string;
}
```

- [ ] **Step 2: 在 `frontend/src/api/dataApi.ts` 追加 archiveApi**

```typescript
// frontend/src/api/dataApi.ts（追加在文件末尾）

import type {
  ArchiveTaskRequest, ArchiveRow, ArchiveMeta, ArchiveKind, MarketType,
} from '@/types/data';

export const archiveApi = {
  startDownload: async (req: ArchiveTaskRequest): Promise<{ task_id: string }> => {
    const resp = await fetch('/api/data/archive/download', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    });
    return resp.json();
  },

  getTask: async (taskId: string): Promise<any> => {
    const resp = await fetch(`/api/data/archive/tasks/${taskId}`);
    return resp.json();
  },

  listSymbols: async (kind: ArchiveKind, market: MarketType): Promise<string[]> => {
    const resp = await fetch(
      `/api/data/archive/symbols?kind=${kind}&market=${market}`,
    );
    const data = await resp.json();
    return data.symbols ?? [];
  },

  queryData: async (
    kind: ArchiveKind, market: MarketType, symbol: string,
    startTime: number, endTime: number, limit = 1000, offset = 0,
  ): Promise<{ total: number; rows: ArchiveRow[]; truncated: boolean }> => {
    const params = new URLSearchParams({
      kind, market, symbol,
      start_time: String(startTime), end_time: String(endTime),
      limit: String(limit), offset: String(offset),
    });
    const resp = await fetch(`/api/data/archive/data?${params}`);
    return resp.json();
  },

  getMeta: async (
    kind: ArchiveKind, market: MarketType, symbol: string,
  ): Promise<ArchiveMeta | null> => {
    const resp = await fetch(`/api/data/archive/meta/${kind}/${market}/${symbol}`);
    const data = await resp.json();
    return data.meta;
  },

  deleteData: async (
    kind: ArchiveKind, market: MarketType, symbol: string,
  ): Promise<void> => {
    await fetch(
      `/api/data/archive/data?kind=${kind}&market=${market}&symbol=${symbol}`,
      { method: 'DELETE' },
    );
  },
};
```

- [ ] **Step 3: 验证编译通过**

Run: `cd frontend && bun run build`
Expected: build succeeds, no TS error

- [ ] **Step 4: 提交**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add frontend/src/api/dataApi.ts frontend/src/types/data.ts
git commit -m "feat(archive): frontend API client + types for 6 endpoints"
```

---

## Task 16: 前端 `DataCollectionPage` 多选对话框

**Files:**
- Modify: `frontend/src/pages/data/DataCollectionPage.tsx`

- [ ] **Step 1: 在"创建任务"对话框加 kind 多选 + market 单选**

找到 `DataCollectionPage` 中现有"创建采集任务"的对话框/Modal 组件，追加以下 state 与 UI：

```tsx
// 追加 state（在 useState 集中位置）
const [archiveKinds, setArchiveKinds] = useState<ArchiveKind[]>(['aggTrades']);
const [archiveMarket, setArchiveMarket] = useState<MarketType>('spot');
const [archiveInterval, setArchiveInterval] = useState<string>('1h');
const [taskType, setTaskType] = useState<'kline' | 'archive'>('kline');
```

在对话框里加一个 **数据源类型** 单选 tab（`kline` 现有 / `archive` 新增），切换显示对应字段：

```tsx
{taskType === 'archive' && (
  <div className="archive-form">
    <label>数据种类（可多选）</label>
    <div className="kind-checkboxes">
      {ARCHIVE_KINDS.map(k => (
        <label key={k}>
          <input
            type="checkbox"
            checked={archiveKinds.includes(k)}
            onChange={e => {
              setArchiveKinds(prev =>
                e.target.checked ? [...prev, k] : prev.filter(x => x !== k)
              );
            }}
          />
          {k}
        </label>
      ))}
    </div>

    <label>市场</label>
    <div className="market-radios">
      {(['spot', 'um', 'cm'] as MarketType[]).map(m => (
        <label key={m}>
          <input
            type="radio"
            checked={archiveMarket === m}
            onChange={() => setArchiveMarket(m)}
          />
          {m}
        </label>
      ))}
    </div>

    {archiveKinds.some(k => KLINE_ARCHIVE_KINDS.includes(k)) && (
      <>
        <label>Interval（K 线类必选）</label>
        <select value={archiveInterval} onChange={e => setArchiveInterval(e.target.value)}>
          {ARCHIVE_INTERVALS.map(i => <option key={i} value={i}>{i}</option>)}
        </select>
      </>
    )}
  </div>
)}
```

修改提交按钮的 `onClick`，根据 `taskType` 走不同分支：

```tsx
const handleSubmit = async () => {
  if (taskType === 'kline') {
    // ... 现有 K 线提交逻辑保持不变
  } else {
    // 归档采集：按 kind 拆成多次调用（避免单任务 IO 集中）
    for (const kind of archiveKinds) {
      await archiveApi.startDownload({
        symbols: symbols.split(',').map(s => s.trim()),
        kind, market: archiveMarket,
        start_date: startDate, end_date: endDate,
        mode: 'inc',
        interval: KLINE_ARCHIVE_KINDS.includes(kind) ? archiveInterval : undefined,
      });
    }
    message.success(`已提交 ${archiveKinds.length} 个归档任务`);
    setDialogOpen(false);
  }
};
```

- [ ] **Step 2: 验证编译通过**

Run: `cd frontend && bun run build`
Expected: build succeeds

- [ ] **Step 3: 手动验证（可选）**

启动后端 `cd backend && uvicorn main:app --reload` + 前端 `cd frontend && bun run dev`，打开 `DataCollectionPage`，确认：
- 顶部多出"数据源类型"单选（kline / archive）
- 选 archive 后显示 7 个 kind 多选 + 3 个 market 单选 + interval（仅 K 线类显示）

- [ ] **Step 4: 提交**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add frontend/src/pages/data/DataCollectionPage.tsx
git commit -m "feat(archive): DataCollectionPage multi-select for 7 kinds × 3 markets"
```

---

## Task 17: 前端 `DataManagementPage` 归档浏览 Tab

**Files:**
- Modify: `frontend/src/pages/data/DataManagementPage.tsx`

- [ ] **Step 1: 在 `DataManagementPage` 加 "归档数据" Tab**

现有 Tab 集合是 `[K线现货, K线合约]`。在 Tab 数组追加 `"归档数据"`，对应的 Tab Pane 内容用以下骨架：

```tsx
<TabPane tab="归档数据" key="archive">
  <div className="archive-browser">
    <div className="left-tree">
      <h4>数据源</h4>
      <Tree
        treeData={ARCHIVE_KINDS.map(kind => ({
          title: kind, key: kind,
          children: (['spot', 'um', 'cm'] as MarketType[]).map(market => ({
            title: market, key: `${kind}__${market}`,
          })),
        }))}
        onSelect={(_, info) => {
          const [kind, market] = (info.node.key as string).split('__');
          setSelectedKind(kind as ArchiveKind);
          setSelectedMarket(market as MarketType);
        }}
      />
    </div>

    <div className="right-content">
      <DatePicker.RangePicker
        onChange={(dates) => {
          if (dates) {
            setTimeRange([
              dates[0]!.valueOf(), dates[1]!.valueOf() + 86400000,
            ]);
          }
        }}
      />
      <Button
        onClick={async () => {
          const data = await archiveApi.queryData(
            selectedKind, selectedMarket, selectedSymbol,
            timeRange[0], timeRange[1], 1000, 0,
          );
          setRows(data.rows);
          message.info(`共 ${data.total} 行${data.truncated ? '（已截断到 1M）' : ''}`);
        }}
      >查询</Button>

      <Table
        dataSource={rows.map((r, i) => ({ key: i, ...r }))}
        columns={Object.keys(rows[0] ?? {}).map(c => ({ title: c, dataIndex: c }))}
        scroll={{ x: true, y: 400 }}
        pagination={{ pageSize: 100 }}
      />
    </div>
  </div>
</TabPane>
```

加 state：

```tsx
const [selectedKind, setSelectedKind] = useState<ArchiveKind>('aggTrades');
const [selectedMarket, setSelectedMarket] = useState<MarketType>('spot');
const [selectedSymbol, setSelectedSymbol] = useState<string>('BTCUSDT');
const [timeRange, setTimeRange] = useState<[number, number]>([0, Date.now()]);
const [rows, setRows] = useState<ArchiveRow[]>([]);
```

- [ ] **Step 2: 验证编译通过**

Run: `cd frontend && bun run build`
Expected: build succeeds

- [ ] **Step 3: 提交**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add frontend/src/pages/data/DataManagementPage.tsx
git commit -m "feat(archive): DataManagementPage archive browse tab"
```

---

## Task 18: Self-check 脚本

**Files:**
- Create: `backend/scripts/check_archive.py`

- [ ] **Step 1: 实现 self-check**

```python
# backend/scripts/check_archive.py
"""归档数据采集 self-check（按 Ponytail 约定：非平凡逻辑留 1 个可运行 check）。

用法: cd backend && .venv/bin/python scripts/check_archive.py
预期: 拉 1 天 BTCUSDT aggTrades + 写入 Parquet + 读回校验 + 打印 _meta.json
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
import tempfile
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)


def main() -> int:
    from exchange.binance.archive.kinds import ArchiveKind, MarketType
    from exchange.binance.archive.factory import BinanceArchiveFactory

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        logger.info("Base dir: %s", base)
        fetcher = BinanceArchiveFactory.create(
            ArchiveKind.AGG_TRADES, MarketType.SPOT,
            base_dir=base, symbol='BTCUSDT',
        )
        result = fetcher.collect_data(
            symbols=['BTCUSDT'],
            start='2024-12-01', end='2024-12-01',
            mode='full',
        )
        logger.info("collect_data result: %s", result)
        assert result['files_added'] >= 1, f"expected >=1 file, got {result}"

        from exchange.binance.archive.archive_meta import read_meta
        meta = read_meta(fetcher.save_dir)
        logger.info("meta: %s", json.dumps(meta, ensure_ascii=False, indent=2))
        assert meta is not None
        assert meta['symbol'] == 'BTCUSDT'
        assert meta['total_rows'] > 0

        # 读回校验
        out = fetcher.read_range('BTCUSDT', 0, 2**63 - 1, limit=10, offset=0)
        logger.info("read_range total=%d, sample rows=%d", out['total'], len(out['rows']))
        assert out['total'] > 0
        assert len(out['rows']) > 0

        logger.info("Self-check PASSED")
        return 0


if __name__ == '__main__':
    sys.exit(main())
```

- [ ] **Step 2: 跑 self-check（需要网络）**

Run: `cd backend && .venv/bin/python scripts/check_archive.py`
Expected: `Self-check PASSED`（末尾 log）

- [ ] **Step 3: 提交**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add backend/scripts/check_archive.py
git commit -m "feat(archive): self-check script for end-to-end verification"
```

---

## Task 19: 回归测试 + K 线集成校验

**Files:** 无新增；跑测试

- [ ] **Step 1: 跑全量后端测试**

Run: `cd backend && .venv/bin/python -m pytest tests/ -v --tb=short 2>&1 | tail -100`
Expected: 0 新增 failure（与基线 a0caf76 对比）

- [ ] **Step 2: 跑前端 build**

Run: `cd frontend && bun run build`
Expected: build succeeds

- [ ] **Step 3: 跑 K 线相关的 3 个关键回归（确认未受影响）**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
.venv/bin/python -m pytest tests/unit/collector/ tests/unit/exchange/binance/ -v 2>&1 | tail -50
```

Expected: 全部 PASS

- [ ] **Step 4: 若有新增 failure，按本仓库惯例修复**

按 `AGENTS.md` "根据 pytest 结果修复代码" 流程：

> 如果 pytest 运行失败,需要根据失败的信息来修复代码,不要为了兼容而修改,需要真实解决问题,如果测试不合理修改测试脚本,如果业务代码不合理修改业务代码。

- [ ] **Step 5: 若有修改，提交（否则跳过）**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git status
# 若有改动：
git add -A
git commit -m "fix(archive): regression test fixes"
```

---

## Task 20: 文档与最终 commit

**Files:**
- Modify: `backend/exchange/binance/archive/__init__.py`（docstring 升级）

- [ ] **Step 1: 更新 `__init__.py` docstring 与导出**

```python
# backend/exchange/binance/archive/__init__.py
"""Binance 历史归档（Tick + K 线）下载体系。

支持 7 种归档数据 × 3 个市场 = 21 种组合:
    aggTrades / trades / bookDepth / bookTicker
    markPriceKlines / indexPriceKlines / premiumIndexKlines
    ×
    spot / futures/um / futures/cm

全部只入 Parquet 分区（spec §3.1），不建 SQL 表。
不碰 realtime 引擎。
不修改现有 K 线数据流。
"""
from exchange.binance.archive.kinds import (
    ArchiveKind, MarketType,
    build_zip_url, get_save_dir, KIND_INTERVALS,
)
from exchange.binance.archive.factory import BinanceArchiveFactory

__all__ = [
    'ArchiveKind', 'MarketType',
    'build_zip_url', 'get_save_dir', 'KIND_INTERVALS',
    'BinanceArchiveFactory',
]
```

- [ ] **Step 2: 跑全量测试 + self-check + 前端 build 三重确认**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
cd backend && .venv/bin/python -m pytest tests/ 2>&1 | tail -5
cd backend && .venv/bin/python scripts/check_archive.py
cd ../frontend && bun run build
```

Expected: pytest 0 failure + self-check PASSED + bun build succeed

- [ ] **Step 3: 最终 commit + 推送（用户明确要求时才 push）**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add -A
git status
git commit -m "docs(archive): finalize __init__ docstring" || echo "nothing to commit"
git log --oneline -25
```

---

## 自审报告

**1. Spec coverage**（spec 8 个章节逐项对应 task）：

| Spec 章节 | 覆盖 task |
|---|---|
| §1 背景与目标（非目标 / 验收） | Task 19（验收） + 全文范围对齐 |
| §2 整体架构 | Task 1, 2, 3 |
| §3 数据模型 & 存储 | Task 1, 4, 5, 6, 7, 8, 9, 10, 11 |
| §4 采集器设计 | Task 2, 3, 5-11 |
| §5 API & 前端 | Task 13, 15, 16, 17 |
| §6 错误处理、测试、回退 | Task 18, 19, 20 |
| §7 实施顺序 | 严格按本 plan 20 个 task |
| §8 风险 & 缓解 | Task 5, 8, 9-11（schema 校验 / 类型保护）；Task 19（回归） |

**2. Placeholder scan**：未发现 "TBD / TODO / implement later / fill in details"。

**3. Type consistency**：
- `ArchiveKind` 7 个值在 Task 1 / 3 / 5-11 / 12 全部一致
- `MarketType` 3 个值一致
- `BaseBinanceArchiveDownloader` 方法签名（`read_range`, `_calculate_missing_ranges`, `save_instrument`, `get_daily_archive`）在 Task 2 定义 → 后续 fetcher 子类（Task 5-11）调用一致
- 6 个 REST 端点路径（spec §5.1）在 Task 13 与 Task 15-17 严格对齐

---

**完成此 plan 后**：调用 `superpowers:executing-plans` 或 `superpowers:subagent-driven-development` 子 skill 开始实施。
