"""
独立数据下载器模块

提供不依赖 FastAPI 服务的数据下载功能，包括：
- 直接从币安/OKX 下载数据
- 直接保存到数据库
- 合并写入 source 单文件 Parquet（回测实际读取口径）
- 实时进度更新
- 失败重试机制
"""

import asyncio
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from collector.db.models import decimal_or_zero
from exchange.binance.downloader import BinanceDownloader
from utils.data_utils import _find_parquet_file, _infer_ts_scale
from utils.logger import LogType, get_logger
from utils.parquet_utils import append_to_parquet, load_from_parquet
from utils.time_parser import get_date_range

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)

if TYPE_CHECKING:
    from collections.abc import Callable

    import pandas as pd


# ---------------------------------------------------------------------------
# source parquet 合并锁
# ---------------------------------------------------------------------------

# 进程内按 (symbol, interval, market_dir) 粒度的合并锁，防止并发下载同一文件互相覆盖
# ponytail: 仅进程内互斥；多进程下载方（uvicorn 多 worker/子进程池）无防护，
# 靠 append_to_parquet 的时间戳去重兜底。若出现多进程写同一文件的场景，升级为 fcntl 文件锁
_merge_locks: dict[str, threading.Lock] = {}
_merge_locks_guard = threading.Lock()


def _merge_lock(key: str) -> threading.Lock:
    with _merge_locks_guard:
        return _merge_locks.setdefault(key, threading.Lock())


class StandaloneDownloadProgress:
    """独立下载进度信息"""

    def __init__(self, symbol: str, interval: str):
        self.symbol = symbol
        self.interval = interval
        self.status: str = "pending"
        self.progress: float = 0.0
        self.message: str = "等待下载"
        self.current_date: str | None = None
        self.total_dates: int = 0
        self.completed_dates: int = 0

    def update(
        self,
        status: str | None = None,
        progress: float | None = None,
        message: str | None = None,
        current_date: str | None = None,
    ):
        """更新进度信息"""
        if status:
            self.status = status
        if progress is not None:
            self.progress = progress
        if message:
            self.message = message
        if current_date:
            self.current_date = current_date
            self.completed_dates += 1


class StandaloneDataDownloader:
    """独立数据下载器，不依赖 FastAPI 服务"""

    def __init__(self):
        """初始化独立下载器（数据落库为副本，并合并进回测读取的 source Parquet）"""
        self.temp_dir = Path(__file__).parent.parent / "data" / "temp"
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        # 延迟初始化下载器，避免在初始化时调用API获取交易对列表
        self._spot_downloader = None
        self._futures_downloader = None

    @property
    def spot_downloader(self):
        """延迟初始化现货下载器"""
        if self._spot_downloader is None:
            self._spot_downloader = BinanceDownloader(
                save_dir=self.temp_dir,
                candle_type="spot",
                symbols=[],
            )
        return self._spot_downloader

    @property
    def futures_downloader(self):
        """延迟初始化合约下载器"""
        if self._futures_downloader is None:
            self._futures_downloader = BinanceDownloader(
                save_dir=self.temp_dir,
                candle_type="futures",
                symbols=[],
            )
        return self._futures_downloader

    # ------------------------------------------------------------------
    # 主下载入口
    # ------------------------------------------------------------------

    async def download_data(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime,
        crypto_type: str = "spot",
        progress_callback: Callable[[StandaloneDownloadProgress], None] | None = None,
    ) -> bool:
        """
        直接下载数据到数据库与 source parquet

        参数：
            symbol: 交易对（如 BTCUSDT）
            interval: 时间周期（如 15m, 1h）
            start_time: 开始时间
            end_time: 结束时间
            crypto_type: 交易类型（spot/futures）
            progress_callback: 进度回调函数

        返回：
            bool: 是否下载成功
        """
        normalized_symbol = symbol.replace("/", "")
        downloader = self.spot_downloader if crypto_type == "spot" else self.futures_downloader

        progress = StandaloneDownloadProgress(normalized_symbol, interval)
        progress.update(status="downloading", message="开始下载数据")
        if progress_callback:
            progress_callback(progress)

        try:
            start_date = start_time.strftime("%Y-%m-%d")
            end_date = end_time.strftime("%Y-%m-%d")
            date_range = get_date_range(start_date, end_date)
            progress.total_dates = len(date_range)

            logger.info(
                f"开始下载 {normalized_symbol} {interval} 数据，"
                f"日期范围: {start_date} ~ {end_date}，共 {len(date_range)} 天"
            )

            success_count = 0
            skipped_count = 0
            for idx, date in enumerate(date_range):
                try:
                    progress.current_date = date
                    progress.update(
                        status="downloading",
                        message=f"正在下载 {date} 的数据...",
                        current_date=date,
                    )
                    if progress_callback:
                        progress.progress = (idx / len(date_range)) * 100
                        progress_callback(progress)

                    # skip 目标是回测实际读的 source parquet，不是 DB 副本
                    if self._check_data_exists(normalized_symbol, interval, date, crypto_type):
                        logger.info(f"✓ {date} 数据已存在，跳过下载")
                        skipped_count += 1
                        success_count += 1
                        continue

                    df = await downloader.get_daily_klines(normalized_symbol, interval, date)

                    if df is not None and not df.empty:
                        # 落库为副本口径
                        self._save_to_database(df, normalized_symbol, interval, crypto_type)

                        # 合并进回测实际读取的 source Parquet（检查/回测同源闭环）
                        self._merge_to_source_parquet(df, normalized_symbol, interval, crypto_type)

                        success_count += 1
                        logger.info(f"✓ {date} 数据下载成功: {len(df)} 条")
                    else:
                        logger.warning(f"⚠ {date} 无数据")

                except Exception as e:
                    logger.error(f"✗ {date} 下载失败: {e}")
                    continue

            progress.update(
                status="completed" if success_count > 0 else "failed",
                progress=100.0,
                message=f"下载完成，成功 {success_count}/{len(date_range)} 天 (跳过 {skipped_count} 天)",
            )
            if progress_callback:
                progress_callback(progress)

            logger.info(
                f"下载完成: {normalized_symbol} {interval}，"
                f"成功 {success_count}/{len(date_range)} 天 (跳过 {skipped_count} 天已存在的数据)"
            )

            return success_count > 0

        except Exception as e:
            logger.error(f"下载过程发生错误: {e}")
            progress.update(status="failed", message=f"下载失败: {e}")
            if progress_callback:
                progress_callback(progress)
            return False

    # ------------------------------------------------------------------
    # 存在性检查（查 source parquet）
    # ------------------------------------------------------------------

    def _check_data_exists(self, symbol: str, interval: str, date: str, crypto_type: str) -> bool:
        """
        检查指定日期的数据是否已存在于回测实际读取的 source Parquet 文件

        skip 的语义是"目标存储已有该日数据"——目标存储即回测读的单文件
        parquet（与完整性检查/回测加载同源）。此前查 DB 且用毫秒整型过滤
        纳秒 BIGINT 列恒为 False（重复下载）；若改回查 DB，"DB 有但 parquet
        缺"的存量日期会被永远 skip，检查永远报缺。
        """
        try:
            market_dir = "spot" if crypto_type == "spot" else "future"
            file_path = _find_parquet_file(symbol, interval, market_dir)
            if not file_path.exists():
                return False

            df = load_from_parquet(file_path, columns=["timestamp"])
            if df.empty:
                return False

            # 按文件实际单位换算日期边界（存量文件 ns/us 不一，由量级推断）
            scale = _infer_ts_scale(float(df["timestamp"].max()))
            date_dt = datetime.strptime(date, "%Y-%m-%d")
            start_ts = int(date_dt.timestamp() * scale)
            end_ts = int((date_dt + timedelta(days=1)).timestamp() * scale)

            count = int(((df["timestamp"] >= start_ts) & (df["timestamp"] < end_ts)).sum())
            return count > 0

        except Exception as e:
            logger.error(f"检查数据存在性失败: {e}")
            return False

    # ------------------------------------------------------------------
    # source parquet 合并写入
    # ------------------------------------------------------------------

    def _merge_to_source_parquet(self, df: pd.DataFrame, symbol: str, interval: str, crypto_type: str) -> bool:
        """
        把新下载的 K 线合并进回测实际读取的 source 单文件 Parquet

        这是"自动下载→回测可用"闭环的落盘端：完整性检查与回测加载读的都是
        这个文件，只写 DB 不写它就会出现"下载完成仍报不完整"。

        只保留回测需要的 7 列；同时间戳以新行为准（append_to_parquet 的
        keep="last"），老文件多出的辅助列在新行上是 NaN，对 OHLCV 驱动的
        回测无实质影响。
        """
        try:
            merge_df = df[["open_time", "open", "high", "low", "close", "volume"]].copy()

            # open_time 单位不定（Binance K 线为毫秒），统一换算为纳秒命名 timestamp，
            # 与存量 source 文件的纳秒口径对齐（混单位会让排序/过滤把新数据漂移到过去）
            open_time = merge_df.pop("open_time").astype("int64")
            scale = _infer_ts_scale(float(open_time.max()))
            merge_df["timestamp"] = open_time * (1_000_000_000 // scale)
            merge_df["symbol"] = symbol
            merge_df = merge_df[["timestamp", "open", "high", "low", "close", "volume", "symbol"]]

            market_dir = "spot" if crypto_type == "spot" else "future"
            file_path = _find_parquet_file(symbol, interval, market_dir)

            with _merge_lock(f"{symbol}_{interval}_{market_dir}"):
                return append_to_parquet(merge_df, file_path)

        except Exception as e:
            logger.error(f"合并到 source Parquet 失败: {symbol} {interval}: {e}")
            return False

    # ------------------------------------------------------------------
    # DB 副本写入（timestamp 纳秒整型）
    # ------------------------------------------------------------------

    def _save_to_database(self, df: pd.DataFrame, symbol: str, interval: str, crypto_type: str) -> bool:
        """保存数据到数据库（副本口径，供数据管理页查询）"""
        from collector.db.database import SessionLocal, init_database_config
        from collector.db.models import CryptoFutureKline, CryptoSpotKline

        try:
            init_database_config()

            from collector.db.database import engine as db_engine

            if db_engine is None:
                logger.error("数据库引擎未初始化")
                return False

            db = SessionLocal(bind=db_engine)

            try:
                Model = CryptoSpotKline if crypto_type == "spot" else CryptoFutureKline

                records = []
                # open_time 单位不保证毫秒（data.binance.vision 日归档实测为微秒）：
                # 按整列量级推断单位后统一换算纳秒，与 _merge_to_source_parquet 同口径。
                # 此前硬编码 *1_000_000 把微秒当毫秒，落库值超出 SQLite INTEGER
                # 上限（2^63-1）直接报 "Python int too large to convert to SQLite INTEGER"
                scale = _infer_ts_scale(float(df["open_time"].max()))
                ns_multiplier = 1_000_000_000 // scale
                for _, row in df.iterrows():
                    timestamp_ns = int(row["open_time"]) * ns_multiplier
                    # 幂等 key 采用换算后的纳秒值：同根 K 线同单位重跑 key 不变，
                    # on_conflict_do_nothing 才能生效（毫秒时代的历史旧 key 不同单位，不迁移）
                    unique_kline = f"{symbol}_{interval}_{timestamp_ns}"

                    records.append(
                        {
                            "symbol": symbol,
                            "interval": interval,
                            # P2-14 起 timestamp 列为 BIGINT 纳秒整型；open_time 单位不定
                            # （实测微秒），落库统一换算纳秒保证口径一致
                            "timestamp": timestamp_ns,
                            "open": decimal_or_zero(row["open"]),
                            "high": decimal_or_zero(row["high"]),
                            "low": decimal_or_zero(row["low"]),
                            "close": decimal_or_zero(row["close"]),
                            "volume": decimal_or_zero(row["volume"]),
                            "unique_kline": unique_kline,
                            "data_source": "binance",
                        }
                    )

                if records:
                    from sqlalchemy.dialects.sqlite import insert

                    stmt = insert(Model).values(records)
                    stmt = stmt.on_conflict_do_nothing(index_elements=["unique_kline"])

                    result = db.execute(stmt)
                    db.commit()
                    logger.info(
                        f"[_save_to_database] 保存 {len(records)} 条记录到数据库: {symbol} {interval}, 影响行数: {result.rowcount}"
                    )

                    verify_count = db.query(Model).filter(Model.symbol == symbol, Model.interval == interval).count()
                    logger.info(f"[_save_to_database] 验证: 数据库中 {symbol} {interval} 共有 {verify_count} 条记录")

                    return True

                return False

            except Exception as e:
                db.rollback()
                logger.error(f"保存到数据库失败: {e}")
                return False
            finally:
                db.close()

        except Exception as e:
            logger.error(f"数据库操作失败: {e}")
            return False

    # ------------------------------------------------------------------
    # 同步接口
    # ------------------------------------------------------------------

    def download_sync(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime,
        crypto_type: str = "spot",
        progress_callback: Callable[[StandaloneDownloadProgress], None] | None = None,
    ) -> bool:
        """同步接口下载数据"""
        return asyncio.run(
            self.download_data(
                symbol=symbol,
                interval=interval,
                start_time=start_time,
                end_time=end_time,
                crypto_type=crypto_type,
                progress_callback=progress_callback,
            )
        )
