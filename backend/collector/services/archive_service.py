"""归档数据业务编排层。

薄编排层，不做实际下载逻辑。所有下载走 fetcher；
任务调度走现有 task_manager；元数据走 archive_meta。
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from exchange.binance.archive.archive_meta import read_meta
from exchange.binance.archive.factory import BinanceArchiveFactory
from exchange.binance.archive.kinds import (
    ArchiveKind,
    MarketType,
    get_save_dir,
    KIND_INTERVALS,
)
from collector.utils.task_manager import task_manager
from utils.logger import get_logger, LogType

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)


# 7 个 kind → task_type 枚举, 跟 scheduled_tasks.task_type 字段对齐
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
        mode: Literal['inc', 'full'] = 'inc',
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
            raise ValueError(
                f"kind={kind.value} requires interval in {allowed_intervals}, got {interval!r}"
            )

        task_type = KIND_TASK_TYPE[kind]
        task_id = task_manager.create_task(
            task_type=task_type,
            params={
                'symbols': symbols,
                'market': market.value,
                'start_date': start_date,
                'end_date': end_date,
                'mode': mode,
                'interval': interval,
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
        return sorted([p.name for p in base.iterdir() if p.is_dir()])
