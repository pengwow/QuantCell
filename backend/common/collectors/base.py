"""
基础收集器模块

提供数据采集的抽象基类，定义数据收集的通用接口和功能。

主要类:
    - BaseCollector: 数据采集器抽象基类

作者: QuantCell Team
版本: 1.0.0
日期: 2026-02-12
"""

import abc
import datetime
import time
from pathlib import Path
from typing import Iterable, Optional, Type, Union

import pandas as pd
from joblib import Parallel, delayed
from loguru import logger
from tqdm import tqdm


class BaseCollector(abc.ABC):
    """基础收集器类，定义数据收集的通用接口和功能"""

    CACHE_FLAG = "CACHED"
    NORMAL_FLAG = "NORMAL"

    DEFAULT_START_DATETIME_1D = pd.Timestamp("2000-01-01")
    DEFAULT_START_DATETIME_1MIN = pd.Timestamp(datetime.datetime.now() - pd.Timedelta(days=30))
    DEFAULT_END_DATETIME_1D = pd.Timestamp(datetime.datetime.now() + pd.Timedelta(days=1))
    DEFAULT_END_DATETIME_1MIN = DEFAULT_END_DATETIME_1D

    INTERVAL_1min = "1min"
    INTERVAL_5min = "5min"
    INTERVAL_15min = "15min"
    INTERVAL_30min = "30min"
    INTERVAL_1h = "1h"
    INTERVAL_4h = "4h"
    INTERVAL_1d = "1d"

    def __init__(
        self,
        save_dir: Union[str, Path],
        start=None,
        end=None,
        interval="1d",
        max_workers=1,
        max_collector_count=2,
        delay=0,
        check_data_length: Optional[int] = None,
        limit_nums: Optional[int] = None,
        mode='inc',
    ):
        """
        初始化收集器

        :param save_dir: 数据保存目录
        :param start: 开始时间
        :param end: 结束时间
        :param interval: 时间间隔，如'1m', '1h', '1d'等
        :param max_workers: 最大工作线程数
        :param max_collector_count: 最大收集次数
        :param delay: 请求延迟时间（秒）
        :param check_data_length: 数据长度检查阈值
        :param limit_nums: 限制收集的标的数量，用于调试
        :param mode: 下载模式，可选'inc'（增量）或'full'（全量），默认'inc'
        """
        self.save_dir = Path(save_dir).expanduser().resolve()
        self.save_dir.mkdir(parents=True, exist_ok=True)

        self.delay = delay
        self.max_workers = max_workers
        self.max_collector_count = max_collector_count
        self.mini_symbol_map: dict = {}
        self.interval = interval
        self.check_data_length = max(int(check_data_length) if check_data_length is not None else 0, 0)
        self.mode = mode

        self.start_datetime = self.normalize_start_datetime(start)
        self.end_datetime = self.normalize_end_datetime(end)

        self.instrument_list = sorted(set(self.get_instrument_list()))

        if limit_nums is not None:
            try:
                self.instrument_list = self.instrument_list[: int(limit_nums)]
            except Exception as e:
                logger.warning(f"无法使用limit_nums={limit_nums}，该参数将被忽略")

    def normalize_start_datetime(self, start_datetime: Optional[Union[str, pd.Timestamp]] = None):
        """标准化开始时间"""
        return (
            pd.Timestamp(str(start_datetime))
            if start_datetime
            else getattr(self, f"DEFAULT_START_DATETIME_{self.interval.upper()}")
        )

    def normalize_end_datetime(self, end_datetime: Optional[Union[str, pd.Timestamp]] = None):
        """标准化结束时间"""
        return (
            pd.Timestamp(str(end_datetime))
            if end_datetime
            else getattr(self, f"DEFAULT_END_DATETIME_{self.interval.upper()}")
        )

    @abc.abstractmethod
    def get_instrument_list(self):
        """获取标的列表"""
        raise NotImplementedError("请重写get_instrument_list方法")

    @abc.abstractmethod
    def normalize_symbol(self, symbol: str):
        """标准化标的代码"""
        raise NotImplementedError("请重写normalize_symbol方法")

    @abc.abstractmethod
    def get_data(
        self, symbol: str, interval: str, start_datetime: pd.Timestamp, end_datetime: pd.Timestamp, progress_callback=None
    ) -> pd.DataFrame:
        """获取标的数据

        :param symbol: 标的代码
        :param interval: 时间间隔
        :param start_datetime: 开始时间
        :param end_datetime: 结束时间
        :param progress_callback: 进度回调函数
        :return: 标的数据DataFrame
        """
        raise NotImplementedError("请重写get_data方法")

    def sleep(self):
        """休眠指定时间，用于控制请求频率"""
        time.sleep(self.delay)

    def _get_interval_freq(self):
        """将间隔字符串映射到 pandas 频率字符串"""
        interval_map = {
            '1m': 'min',
            '5m': '5min',
            '15m': '15min',
            '30m': '30min',
            '1h': 'H',
            '4h': '4H',
            '1d': 'D'
        }
        return interval_map.get(self.interval, 'D')

    def _generate_complete_date_range(self):
        """生成完整的日期范围"""
        freq = self._get_interval_freq()
        return pd.date_range(start=self.start_datetime, end=self.end_datetime, freq=freq)

    def _calculate_missing_ranges(self, existing_timestamps):
        """计算缺失的日期范围"""
        complete_range = self._generate_complete_date_range()

        if existing_timestamps.empty:
            if not complete_range.empty:
                logger.info(f"没有现有数据，返回完整范围: {complete_range[0]} 至 {complete_range[-1]}")
                return [(complete_range[0], complete_range[-1])]
            else:
                return []

        try:
            existing_timestamps = pd.to_numeric(existing_timestamps, errors='coerce').dropna()

            if existing_timestamps.empty:
                if not complete_range.empty:
                    logger.info(f"没有有效时间戳，返回完整范围: {complete_range[0]} 至 {complete_range[-1]}")
                    return [(complete_range[0], complete_range[-1])]
                else:
                    return []

            existing_datetimes = pd.to_datetime(existing_timestamps, unit='ms', errors='coerce')
            existing_datetimes = existing_datetimes.dropna()

            if existing_datetimes.empty:
                if not complete_range.empty:
                    logger.info(f"无法转换时间戳，返回完整范围: {complete_range[0]} 至 {complete_range[-1]}")
                    return [(complete_range[0], complete_range[-1])]
                else:
                    return []

            missing_dates = complete_range.difference(existing_datetimes)

            if missing_dates.empty:
                logger.info("没有缺失的日期")
                return []

            existing_min = existing_datetimes.min()
            existing_max = existing_datetimes.max()
            logger.info(f"现有数据时间范围: {existing_min} 至 {existing_max}")
            logger.info(f"完整日期范围: {complete_range[0]} 至 {complete_range[-1]}")
            logger.info(f"缺失日期数量: {len(missing_dates)}")

            missing_dates = missing_dates.sort_values()
            ranges = []
            start = missing_dates[0]

            for i in range(1, len(missing_dates)):
                if (missing_dates[i] - missing_dates[i-1]).total_seconds() > self._get_interval_seconds():
                    ranges.append((start, missing_dates[i-1]))
                    start = missing_dates[i]

            ranges.append((start, missing_dates[-1]))

            logger.info(f"计算得到 {len(ranges)} 个缺失数据范围")
            for i, (range_start, range_end) in enumerate(ranges):
                logger.info(f"缺失范围 {i+1}: {range_start} 至 {range_end}")

            return ranges
        except Exception as e:
            logger.error(f"计算缺失范围失败: {e}")
            logger.exception(e)
            if not complete_range.empty:
                logger.info(f"计算失败，返回完整范围: {complete_range[0]} 至 {complete_range[-1]}")
                return [(complete_range[0], complete_range[-1])]
            else:
                return []

    def _get_interval_seconds(self):
        """获取间隔对应的秒数"""
        interval_seconds_map = {
            '1m': 60,
            '5m': 300,
            '15m': 900,
            '30m': 1800,
            '1h': 3600,
            '4h': 14400,
            '1d': 86400
        }
        return interval_seconds_map.get(self.interval, 86400)

    def _simple_collector(self, symbol: str, progress_callback=None):
        """简单收集器，用于单个标的的数据收集"""
        self.sleep()

        normalized_symbol = self.normalize_symbol(symbol)
        instrument_path = self.save_dir.joinpath(f"{normalized_symbol}.csv")

        existing_timestamps = pd.Series([], dtype='int64')
        if self.mode == 'inc' and instrument_path.exists():
            try:
                _old_df = pd.read_csv(instrument_path)
                if not _old_df.empty:
                    if 'date' in _old_df.columns and 'timestamp' not in _old_df.columns:
                        _old_df = _old_df.rename(columns={'date': 'timestamp'})
                    _old_df['timestamp'] = pd.to_numeric(_old_df['timestamp'], errors='coerce')
                    existing_timestamps = _old_df['timestamp'].dropna()
                    logger.info(f"[增量模式] 读取到 {symbol} 的现有数据，包含 {len(existing_timestamps)} 条有效记录")
            except Exception as e:
                logger.error(f"[增量模式] 读取 {symbol} 历史数据失败: {e}")
                logger.exception(e)

        missing_ranges = self._calculate_missing_ranges(existing_timestamps)

        if not missing_ranges:
            logger.info(f"[增量模式] {symbol} 在指定时间范围内数据完整，无需下载")
            return self.NORMAL_FLAG

        all_df = pd.DataFrame()
        for i, (range_start, range_end) in enumerate(missing_ranges):
            logger.info(f"[增量模式] {symbol} 缺失数据范围 {i+1}/{len(missing_ranges)}: {range_start} 至 {range_end}")

            try:
                df = self.get_data(symbol, self.interval, range_start, range_end, progress_callback)

                if df is not None and not df.empty:
                    all_df = pd.concat([all_df, df]) if not all_df.empty else df
                    logger.info(f"[增量模式] 成功下载 {symbol} 数据范围: {range_start} 至 {range_end}, 数据量: {len(df)}条")
                else:
                    logger.warning(f"[增量模式] {symbol} 数据范围 {range_start} 至 {range_end} 下载结果为空")
            except Exception as e:
                logger.error(f"[增量模式] 下载 {symbol} 数据范围 {range_start} 至 {range_end} 失败: {e}")

        if all_df.empty:
            logger.error(f"[增量模式] {symbol} 所有缺失范围下载失败，无数据可保存")
            return self.CACHE_FLAG

        _result = self.NORMAL_FLAG
        if self.check_data_length > 0:
            _result = self.cache_small_data(symbol, all_df)
        if _result == self.NORMAL_FLAG:
            self.save_instrument(symbol, all_df)

        return _result

    def save_instrument(self, symbol, df: pd.DataFrame):
        """保存标的数据到文件"""
        if df is None or df.empty:
            logger.warning(f"{symbol} 数据为空")
            return

        symbol = self.normalize_symbol(symbol)
        instrument_path = self.save_dir.joinpath(f"{symbol}.csv")
        df["symbol"] = symbol

        df['timestamp'] = df['timestamp']
        df = df.drop_duplicates(subset=['timestamp'], keep='last')
        df = df.sort_values('timestamp')

        if self.mode != 'full' and instrument_path.exists():
            _old_df = pd.read_csv(instrument_path)
            if 'date' in _old_df.columns and 'timestamp' not in _old_df.columns:
                _old_df = _old_df.rename(columns={'date': 'timestamp'})
            _old_df['timestamp'] = pd.to_numeric(_old_df['timestamp'], errors='coerce')
            df = pd.concat([_old_df, df], sort=False)
            df = df.drop_duplicates(subset=['timestamp'], keep='last')
            df = df.sort_values('timestamp')

        df_for_save = df.copy()
        df_for_save['timestamp'] = df_for_save['timestamp'].astype(str)
        df_for_save.to_csv(instrument_path, index=False)

        mode_label = "[全量模式]" if self.mode == 'full' else "[增量模式]"
        logger.info(f"{mode_label} 成功将 {symbol} 数据保存到文件: {instrument_path}")

    def cache_small_data(self, symbol, df):
        """缓存数据量较小的标的数据"""
        if len(df) < self.check_data_length:
            logger.warning(f"{symbol} 的数据长度小于 {self.check_data_length}！")
            _temp = self.mini_symbol_map.setdefault(symbol, [])
            _temp.append(df.copy())
            return self.CACHE_FLAG
        else:
            if symbol in self.mini_symbol_map:
                self.mini_symbol_map.pop(symbol)
            return self.NORMAL_FLAG

    def _collector(self, instrument_list, progress_callback=None, completed=0, total=0):
        """批量收集标的数据"""
        error_symbol = []
        failed = 0

        def collect_with_progress(_inst, index):
            nonlocal completed, failed

            def download_progress_callback(symbol, current, total, status):
                if progress_callback:
                    progress_callback(_inst, current, total, failed, status)

            if progress_callback:
                progress_callback(_inst, completed, total, failed)

            result = self._simple_collector(_inst, download_progress_callback)
            completed += 1

            if result != self.NORMAL_FLAG:
                error_symbol.append(_inst)
                failed += 1

            if progress_callback:
                progress_callback(_inst, completed, total, failed)

            return result

        res = Parallel(n_jobs=self.max_workers)(
            delayed(collect_with_progress)(_inst, idx) for idx, _inst in enumerate(instrument_list)
        )

        logger.info(f"收集失败的标的数量: {len(error_symbol)}")
        logger.info(f"当前收集的标的数量: {len(instrument_list)}")
        error_symbol.extend(self.mini_symbol_map.keys())
        return sorted(set(error_symbol))

    def collect_data(self, progress_callback=None):
        """执行数据收集"""
        logger.info(f"[收集开始] 模式: {self.mode}, 标的数量: {len(self.instrument_list)}, 时间范围: {self.start_datetime} 至 {self.end_datetime}")
        instrument_list = self.instrument_list
        total_instruments = len(instrument_list)
        completed = 0
        failed = 0

        start_time = datetime.datetime.now()

        def detailed_progress_callback(symbol, current, total, failed_count, status="downloading"):
            if progress_callback:
                progress_callback(symbol, current, total, failed_count, status)

            overall_progress = (completed + (current / total if total > 0 else 0)) / total_instruments * 100
            logger.info(f"[进度] {symbol} - 当前进度: {current/total*100:.1f}%, 整体进度: {overall_progress:.1f}%, 状态: {status}")

        for i in range(self.max_collector_count):
            if not instrument_list:
                break
            logger.info(f"[收集轮次] 第 {i+1}/{self.max_collector_count} 次获取数据，当前待收集标的数量: {len(instrument_list)}")
            instrument_list = self._collector(instrument_list, detailed_progress_callback, completed, total_instruments)
            logger.info(f"[收集轮次] 第 {i+1} 次收集完成，剩余待收集标的数量: {len(instrument_list)}")

        if self.mini_symbol_map:
            logger.info(f"[缓存处理] 开始处理 {len(self.mini_symbol_map)} 个缓存的小数据量标的")
            for _symbol, _df_list in self.mini_symbol_map.items():
                _df = pd.concat(_df_list, sort=False)
                if not _df.empty:
                    self.save_instrument(_symbol, _df.drop_duplicates(["timestamp"]).sort_values(["timestamp"]))

            logger.warning(f"[缓存处理] 数据长度小于 {self.check_data_length} 的标的列表: {list(self.mini_symbol_map.keys())}")

        elapsed_time = datetime.datetime.now() - start_time

        logger.info(f"[收集完成] 总标的数量: {len(self.instrument_list)}, 收集失败: {len(set(instrument_list))}, 耗时: {elapsed_time.total_seconds():.2f} 秒")
        logger.info(f"[收集结果] 模式: {self.mode}, 成功: {len(self.instrument_list) - len(set(instrument_list))}, 失败: {len(set(instrument_list))}")
