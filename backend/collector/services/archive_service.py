"""归档数据业务编排层。

薄编排层，不做实际下载逻辑。所有下载走 fetcher；
任务调度走现有 task_manager；元数据走 archive_meta。
"""

from __future__ import annotations

import os
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Literal

import pyarrow.parquet as pq

from collector.utils.task_manager import task_manager
from exchange.binance.archive.archive_meta import read_meta
from exchange.binance.archive.factory import BinanceArchiveFactory
from exchange.binance.archive.kinds import (
    KIND_INTERVALS,
    ArchiveKind,
    MarketType,
    get_save_dir,
)
from utils.logger import LogType, get_logger

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)


# 7 个 kind → task_type 枚举, 跟 scheduled_tasks.task_type 字段对齐
KIND_TASK_TYPE: dict[ArchiveKind, str] = {
    ArchiveKind.AGG_TRADES: "archive_agg_trades",
    ArchiveKind.TRADES: "archive_trades",
    ArchiveKind.BOOK_DEPTH: "archive_book_depth",
    ArchiveKind.BOOK_TICKER: "archive_book_ticker",
    ArchiveKind.MARK_KLINES: "archive_mark_klines",
    ArchiveKind.INDEX_KLINES: "archive_index_klines",
    ArchiveKind.PREMIUM_KLINES: "archive_premium_klines",
}


# 数据源根目录下按路径段可认出的 kind。两族布局并存：
#   1) 归档布局 `{base}/{market}/{kind}/{symbol}/_meta.json`（7 个 AI 归档 kind），
#      _meta.json 是权威来源，行数 / 日期直接读它。
#   2) 数据池布局（无任何 _meta.json）：
#      `{base}/crypto/{market}/klines/{interval}/{symbol}.parquet`  → kind `kline`
#      `{base}/{fundingRate|openInterest}/{market}/{symbol}/*.parquet` → 同名 kind
#      只能读 parquet footer 兜底（见 `_parquet_stats`）。
_KIND_ALIASES: dict[str, str] = {"klines": "kline"}
_KLINE_POOL_KIND = "kline"
_KIND_NAMES: frozenset[str] = frozenset(k.value for k in ArchiveKind) | {
    "fundingRate",
    "openInterest",
}


def _kind_of(path: Path, base: Path) -> str | None:
    """从相对路径段里认出 kind（兼容两种层序），认不出返回 None。"""
    try:
        parts = path.relative_to(base).parts
    except ValueError:
        return None
    for part in parts:
        if part in _KIND_ALIASES:
            return _KIND_ALIASES[part]
        if part in _KIND_NAMES:
            return part
    return None


# parquet 里的时间列名不统一：数据池 K 线的常规文件是 `timestamp`，pandas 导出的文件
# （如 crypto/future/klines/1h/BTCUSDT.parquet）没有 timestamp 列、时间落在索引列
# `__index_level_0__`；币安原始列偶见 open_time。
_TIME_COLUMNS: tuple[str, ...] = ("timestamp", "__index_level_0__", "time", "open_time")


def _time_column_index(names: list[str]) -> int | None:
    """按优先级找出时间列下标；都没有返回 None（只算行数，不算日期）。"""
    for candidate in _TIME_COLUMNS:
        if candidate in names:
            return names.index(candidate)
    for index, name in enumerate(names):
        lowered = name.lower()
        if "timestamp" in lowered or lowered.endswith("_time"):
            return index
    return None


def _to_date(value: object) -> str | None:
    """parquet statistics 的 min/max → `YYYY-MM-DD`（UTC）。

    兼容三种形态：
    - `datetime` / `date`：pandas 索引列的 statistics 直接给 Timestamp，`.date()` 即可；
    - epoch 数值：同一 kind 内单位并不统一（spot 池是微秒、future 池多为毫秒），
      所以逐值按量级判 秒 / 毫秒 / 微秒 / 纳秒，不能按路径或 kind 判；
    - ISO 字符串。

    判不出（None / 非时间类型 / 明显不是 epoch 的整数）返回 None —— 绝不填「今天」。
    """
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value).date().isoformat()
        except ValueError:
            return None
    if not isinstance(value, (int, float)):
        return None
    number = float(value)
    # 拒掉 20261107 这类 YYYYMMDD 整数：真实 epoch 秒已 > 1e9（2001 年之后）
    if number < 1e9:
        return None
    if number < 1e11:
        seconds = number  # 秒
    elif number < 1e14:
        seconds = number / 1e3  # 毫秒
    elif number < 1e17:
        seconds = number / 1e6  # 微秒
    else:
        seconds = number / 1e9  # 纳秒
    try:
        return datetime.fromtimestamp(seconds, tz=UTC).date().isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def _parquet_stats(path: Path) -> tuple[int, str | None, str | None]:
    """只读 footer（`read_metadata`，不加载数据）取 (行数, 最早日期, 最晚日期)。

    日期来自时间列的 row-group statistics；statistics 缺失或全 null 时日期为 None，
    行数照算。列 chunk 的下标与扁平 schema 的列下标一致（本仓 parquet 全是扁平表）。
    """
    metadata = pq.read_metadata(path)
    rows = int(metadata.num_rows)
    index = _time_column_index(metadata.schema.names)
    if index is None:
        return rows, None, None
    earliest: str | None = None
    latest: str | None = None
    for group in range(metadata.num_row_groups):
        stats = metadata.row_group(group).column(index).statistics
        if stats is None or not stats.has_min_max:
            continue
        low = _to_date(stats.min)
        high = _to_date(stats.max)
        if low and (earliest is None or low < earliest):
            earliest = low
        if high and (latest is None or high > latest):
            latest = high
    return rows, earliest, latest


def _pool_symbol(kind: str, path: Path) -> str | None:
    """无 meta 的 parquet 属于哪个标的：K 线池是文件名，其余布局是 symbol 目录名。"""
    if kind == _KLINE_POOL_KIND:
        return path.stem or None
    return path.parent.name or None


# 标的简况「累计 bar」口径：只有这几个 kind 的行才是 bar，其余是成交/快照条目
_BAR_KINDS: frozenset[str] = frozenset({"kline", "markPriceKlines", "indexPriceKlines", "premiumIndexKlines"})

# 归档布局里按 interval 落盘的 K 线 kind（文件名 `{sym}-{kind}-{interval}-{date}.parquet`）
_ARCHIVE_KLINE_KINDS: frozenset[str] = frozenset({"markPriceKlines", "indexPriceKlines", "premiumIndexKlines"})

# 周期排序口径（面板「采集口径」按此顺序拼，不按字母序）
_INTERVAL_ORDER: tuple[str, ...] = ("1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "1d")


def _normalize_symbol(symbol: str) -> str:
    """`LTC/USDT` / `LTC-USDT` → `LTCUSDT`（本地目录名与 K 线池文件名的形态）。"""
    return symbol.replace("/", "").replace("-", "").replace("_", "").upper()


def _epoch(value: object) -> float:
    """ISO 字符串 → 时间戳；无法解析返回 -1（用于 updated_at 跨时区比较）。"""
    try:
        return datetime.fromisoformat(str(value)).timestamp()
    except (TypeError, ValueError):
        return -1.0


class ArchiveService:
    """Binance 历史归档数据 (7 种 × 3 个市场) 业务编排层。

    职责:
    - 把"创建下载任务"委托给 task_manager
    - 把"数据查询"委托给 factory 装配的 fetcher
    - 把"元数据读取"委托给 archive_meta
    - "已采集 symbol 列表" = 扫描本地目录
    """

    def __init__(self, base_dir: str | Path, proxy: str | None = None) -> None:
        """初始化服务。

        Args:
            base_dir: 归档数据存储根目录 (例如 'data/source/archive')。
            proxy: HTTP 代理地址, 透传给 fetcher。
        """
        self.base_dir = Path(base_dir)
        self.proxy = proxy

    def create_download_task(
        self,
        symbols: list[str],
        kind: ArchiveKind,
        market: MarketType,
        start_date: str,
        end_date: str,
        mode: Literal["inc", "full"] = "inc",
        interval: str | None = None,
    ) -> str:
        """创建归档下载任务。

        任务被 task_manager 记录并由 worker 异步执行。
        K 线类 (mark/index/premium Klines) 必须传 interval, 且必须在允许的 8 个之内。

        Args:
            symbols: 待下载的交易对列表。
            kind: 归档数据种类。
            market: 市场 (spot/um/cm)。
            start_date: 起始日期 YYYY-MM-DD。
            end_date: 结束日期 YYYY-MM-DD。
            mode: 'inc' 增量 / 'full' 全量。
            interval: K 线类需要的周期 (1m/3m/5m/15m/30m/1h/2h/1d), 非 K 线类忽略。

        Returns:
            str: task_id, 后续用于查进度。

        Raises:
            ValueError: K 线类未传 interval 或 interval 不在允许列表中。
        """
        # K 线类必须传 interval
        allowed_intervals = KIND_INTERVALS[kind]
        if allowed_intervals is not None and interval not in allowed_intervals:
            msg = f"kind={kind.value} requires interval in {allowed_intervals}, got {interval!r}"
            raise ValueError(msg)

        task_type = KIND_TASK_TYPE[kind]
        task_id = task_manager.create_task(
            task_type=task_type,
            params={
                "symbols": symbols,
                "market": market.value,
                "start_date": start_date,
                "end_date": end_date,
                "mode": mode,
                "interval": interval,
            },
        )
        logger.info(
            f"Created {task_type} task {task_id} for {symbols} "
            f"(market={market.value}, {start_date}..{end_date}, mode={mode}, interval={interval})"
        )
        return task_id

    def query_data(
        self,
        kind: ArchiveKind,
        market: MarketType,
        symbol: str,
        start_time: int,
        end_time: int,
        limit: int = 1000,
        offset: int = 0,
    ) -> dict:
        """从本地 Parquet 读取指定区间的数据。

        委托 BinanceArchiveFactory 装配 fetcher, 再调 read_range。
        interval 在这里不传 (K 线 fetcher 内部已经按 symbol 自适应)。

        Args:
            kind: 归档数据种类。
            market: 市场。
            symbol: 交易对。
            start_time: 起始时间 (毫秒)。
            end_time: 结束时间 (毫秒)。
            limit: 分页行数上限。
            offset: 分页偏移。

        Returns:
            dict: {'total': int, 'rows': list[dict], 'truncated': bool}
        """
        fetcher = BinanceArchiveFactory.create(
            kind,
            market,
            base_dir=str(self.base_dir),
            symbol=symbol,
            interval=None,
            proxy=self.proxy,
        )
        return fetcher.read_range(symbol, start_time, end_time, limit, offset)

    def get_meta(
        self,
        kind: ArchiveKind,
        market: MarketType,
        symbol: str,
    ) -> dict | None:
        """读取 (kind, market, symbol) 目录下的 _meta.json。

        Args:
            kind: 归档数据种类。
            market: 市场。
            symbol: 交易对。

        Returns:
            dict | None: meta dict, 不存在或损坏返回 None。
        """
        save_dir = get_save_dir(self.base_dir, market, kind, symbol)
        return read_meta(save_dir)

    def list_symbols(
        self,
        kind: ArchiveKind,
        market: MarketType,
    ) -> list[str]:
        """列出某 (kind, market) 下已采集的 symbols (按字典序排序)。

        实现: 扫描 `base_dir/market/kind/` 下的子目录名。

        Args:
            kind: 归档数据种类。
            market: 市场。

        Returns:
            list[str]: 已采集的 symbol 列表, 目录不存在返回空列表。
        """
        base = self.base_dir / market.value / kind.value
        if not base.exists():
            return []
        # 过滤无 parquet 的空壳目录（只写 _meta.json 的残留）：树上不显示点开为空的 symbol。
        # ponytail: 每 symbol 一次单层 glob，几百个 symbol 可接受；symbol 量级再涨时改成
        # 建 SQLite 索引或目录标记
        return sorted(p.name for p in base.iterdir() if p.is_dir() and any(p.glob("*.parquet")))

    def get_symbol_coverage(
        self,
        symbol: str,
        market: MarketType = MarketType.SPOT,
    ) -> dict[str, Any]:
        """单个标的在某市场下已采集的覆盖情况（标的简况面板用）。

        三族布局一起看，按 kind 汇总：

        - 归档布局 `{market}/{kind}/{symbol}/_meta.json`（7 个 AI kind）：行数/日期读 meta；
          标记/指数/溢价 K 线再从 `{sym}-{kind}-{interval}-{date}.parquet` 文件名认出周期。
        - 数据池 K 线：`crypto/{spot|future}/klines/{interval}/{symbol}.parquet`，周期即目录名，
          行数读 parquet footer（pool 文件的时间列可能是索引列，`_parquet_stats` 已兼容）。
        - 数据池衍生：`{fundingRate|openInterest}/{market}/{symbol}/*.parquet`。

        Returns:
            dict: `{symbol, market, items, total_rows, bar_rows, intervals, latest_date}`；
            items 元素 `{kind, market, intervals, total_rows, earliest_date, latest_date}`。
            `bar_rows` 只累加 K 线类 kind（成交/快照的行不是 bar）。

        ponytail: 每次展开只 stat / 读单个 symbol 的几个目录，不做全树 walk，前端按
        symbol 缓存；symbol 数或 kind 数再涨时再考虑落 SQLite 索引。
        """

        def ensure(kind: str) -> dict[str, Any]:
            return items.setdefault(
                kind,
                {
                    "kind": kind,
                    "market": market.value,
                    "intervals": [],
                    "total_rows": 0,
                    "earliest_date": None,
                    "latest_date": None,
                },
            )

        def add(kind: str, rows: int, earliest: str | None, latest: str | None) -> None:
            item = ensure(kind)
            item["total_rows"] += rows
            if earliest and (item["earliest_date"] is None or earliest < item["earliest_date"]):
                item["earliest_date"] = earliest
            if latest and (item["latest_date"] is None or latest > item["latest_date"]):
                item["latest_date"] = latest

        def add_interval(kind: str, interval: str) -> None:
            intervals = ensure(kind)["intervals"]
            if interval in _INTERVAL_ORDER and interval not in intervals:
                intervals.append(interval)

        norm = _normalize_symbol(symbol)
        items: dict[str, dict[str, Any]] = {}

        # 1) 归档布局（7 个 kind）
        for kind in ArchiveKind:
            for save_dir in self._symbol_dirs(market, kind.value, symbol, norm):
                meta = read_meta(save_dir)
                if not meta:
                    continue
                add(
                    kind.value,
                    int(meta.get("total_rows") or 0),
                    meta.get("earliest_date"),
                    meta.get("latest_date"),
                )
                if kind.value in _ARCHIVE_KLINE_KINDS:
                    for path in save_dir.glob("*.parquet"):
                        parts = path.stem.split("-")
                        if len(parts) >= 3 and parts[1] == kind.value:
                            add_interval(kind.value, parts[2])

        # 2) 数据池 K 线：周期 = 目录名
        pool_market = {"spot": "spot", "um": "future"}.get(market.value)
        kline_root = self.base_dir / "crypto" / pool_market / "klines" if pool_market else None
        if kline_root is not None and kline_root.is_dir():
            for interval_dir in sorted(p for p in kline_root.iterdir() if p.is_dir()):
                path = interval_dir / f"{norm}.parquet"
                if not path.is_file():
                    continue
                try:
                    rows, earliest, latest = _parquet_stats(path)
                except Exception as exc:  # 损坏 / 权限：跳过该周期，不拖垮端点
                    logger.warning(f"读取 parquet footer 失败，跳过 {path}: {exc}")
                    continue
                add(_KLINE_POOL_KIND, rows, earliest, latest)
                add_interval(_KLINE_POOL_KIND, interval_dir.name)

        # 3) 数据池衍生（fundingRate / openInterest）：层序是 {kind}/{market}/{symbol}
        for kind in ("fundingRate", "openInterest"):
            for save_dir in self._pool_symbol_dirs(kind, market, symbol, norm):
                for path in sorted(save_dir.glob("*.parquet")):
                    try:
                        rows, earliest, latest = _parquet_stats(path)
                    except Exception as exc:
                        logger.warning(f"读取 parquet footer 失败，跳过 {path}: {exc}")
                        continue
                    add(kind, rows, earliest, latest)

        for item in items.values():
            item["intervals"].sort(key=_INTERVAL_ORDER.index)
        ordered = [items[k] for k in sorted(items)]
        all_intervals: list[str] = []
        for item in ordered:
            for interval in item["intervals"]:
                if interval not in all_intervals:
                    all_intervals.append(interval)
        return {
            "symbol": norm,
            "market": market.value,
            "items": ordered,
            "total_rows": sum(item["total_rows"] for item in ordered),
            "bar_rows": sum(item["total_rows"] for item in ordered if item["kind"] in _BAR_KINDS),
            "intervals": all_intervals,
            "latest_date": max(
                (item["latest_date"] for item in ordered if item["latest_date"]),
                default=None,
            ),
        }

    def _symbol_dirs(
        self,
        market: MarketType,
        kind: str,
        symbol: str,
        norm: str,
    ) -> list[Path]:
        """归档布局 `{market}/{kind}/{symbol}` 下该标的可能落的目录。

        兼容单段 `LTCUSDT` 与旧的两级 `LTC/USDT`。
        """
        root = self.base_dir / market.value / kind
        candidates = [root / norm]
        if "/" in symbol:
            candidates.append(root / symbol)
        return [path for path in candidates if path.is_dir()]

    def _pool_symbol_dirs(
        self,
        kind: str,
        market: MarketType,
        symbol: str,
        norm: str,
    ) -> list[Path]:
        """数据池布局 `{kind}/{market}/{symbol}` 下该标的可能落的目录（层序与归档布局相反）。"""
        root = self.base_dir / kind / market.value
        candidates = [root / norm]
        if "/" in symbol:
            candidates.append(root / symbol)
        return [path for path in candidates if path.is_dir()]

    def get_watermark(self) -> dict[str, Any]:
        """按 kind 聚合数据源水位与磁盘占用（首屏「数据源水位 / 存储用量」两块卡）。

        统计两族布局（`data/source` 下并存）：

        - **归档布局** `{market}/{kind}/{symbol}/_meta.json`：以 `_meta.json` 为权威来源
          （symbol_count 按目录计，行数与日期直接取 meta 字段）。
        - **数据池布局**（无 `_meta.json`）：`crypto/{market}/klines/{interval}/{symbol}.parquet`
          → kind `kline`；`{fundingRate,openInterest}/{market}/{symbol}/*.parquet` → 同名
          kind。此时读 parquet footer 兜底：`num_rows` 累加进 `total_rows`，时间列
          statistics 的 min/max 换算成日期，symbol_count 按 **distinct symbol** 计（同一
          symbol 的 15m/1h/4h 多个文件只算 1 个标的）。

        兜底口径：同一目录既有 `_meta.json` 又有 parquet 时只按 meta 计一次（不重复叠加
        行数/日期）；statistics 缺失只影响日期（行数与体积照算），日期全取不到就保持
        `None`（前端显示「—」），不填今天；单个文件读不了只 warning 并跳过，不影响端点。

        Returns:
            dict: `{watermarks: [...], storage: [...], total_bytes: int}`，两个数组按 kind 升序。
            watermarks 元素：`{kind, symbol_count, total_rows, earliest_date, latest_date, updated_at}`。
            storage 元素：`{kind, bytes}`。

        ponytail: 仍是一次 `os.walk`，无 meta 的 parquet 只读 footer（`read_metadata`，
        不加载数据）；当前 41 个文件读 footer 毫秒级，文件数上万时改为定期任务落缓存。
        """
        watermarks: dict[str, dict[str, Any]] = {}
        storage: dict[str, int] = {}
        # 无 meta 的 parquet 先攒着，等整棵树走完再读 footer —— 同一目录有没有 _meta.json
        # 要等 files 列表拿全才知道（不能靠 os.walk 的访问顺序）。
        pending: list[tuple[Path, str]] = []
        pool_symbols: dict[str, set[str]] = {}
        base = self.base_dir
        if base.is_dir():
            for root, _dirs, files in os.walk(base):
                root_path = Path(root)
                has_meta = "_meta.json" in files
                for name in files:
                    if name == "_meta.json":
                        meta = read_meta(root_path)
                        kind = str((meta or {}).get("kind") or _kind_of(root_path, base) or "")
                        if meta and kind:
                            self._merge_meta(watermarks, kind, meta)
                    elif name.endswith(".parquet"):
                        kind = _kind_of(root_path, base)
                        if kind is None:
                            continue
                        path = root_path / name
                        try:
                            storage[kind] = storage.get(kind, 0) + path.stat().st_size
                        except OSError:
                            continue
                        if not has_meta:
                            pending.append((path, kind))
            for path, kind in pending:
                try:
                    rows, earliest, latest = _parquet_stats(path)
                except Exception as exc:  # 损坏 / 权限 / 非 parquet：跳过，不拖垮端点
                    logger.warning(f"读取 parquet footer 失败，跳过 {path}: {exc}")
                    continue
                item = self._ensure(watermarks, kind)
                item["total_rows"] += rows
                self._merge_dates(item, earliest, latest)
                symbol = _pool_symbol(kind, path)
                if symbol:
                    pool_symbols.setdefault(kind, set()).add(symbol)
        # symbol_count 在整棵树走完后按 distinct symbol 补上（K 线池同标的多周期只算一个）
        for kind, symbols in pool_symbols.items():
            watermarks[kind]["symbol_count"] += len(symbols)
        return {
            "watermarks": [watermarks[k] for k in sorted(watermarks)],
            "storage": [{"kind": k, "bytes": storage[k]} for k in sorted(storage)],
            "total_bytes": sum(storage.values()),
        }

    @staticmethod
    def _ensure(acc: dict[str, dict[str, Any]], kind: str) -> dict[str, Any]:
        """取出（必要时新建）某个 kind 的水位累积条目。"""
        return acc.setdefault(
            kind,
            {
                "kind": kind,
                "symbol_count": 0,
                "total_rows": 0,
                "earliest_date": None,
                "latest_date": None,
                "updated_at": None,
            },
        )

    @staticmethod
    def _merge_dates(item: dict[str, Any], earliest: str | None, latest: str | None) -> None:
        """把一对 YYYY-MM-DD 合进水位条目（取全局 min / max，None 直接忽略）。"""
        if earliest and (item["earliest_date"] is None or earliest < item["earliest_date"]):
            item["earliest_date"] = earliest
        if latest and (item["latest_date"] is None or latest > item["latest_date"]):
            item["latest_date"] = latest

    @staticmethod
    def _merge_meta(acc: dict[str, dict[str, Any]], kind: str, meta: dict[str, Any]) -> None:
        """把单个 `_meta.json` 合进按 kind 累积的水位条目（sum 行数 / min-max 日期）。"""
        item = ArchiveService._ensure(acc, kind)
        item["symbol_count"] += 1
        try:
            item["total_rows"] += int(meta.get("total_rows") or 0)
        except (TypeError, ValueError):
            pass
        ArchiveService._merge_dates(item, meta.get("earliest_date"), meta.get("latest_date"))
        updated = meta.get("updated_at")
        if updated and _epoch(updated) > _epoch(item["updated_at"]):
            item["updated_at"] = updated
