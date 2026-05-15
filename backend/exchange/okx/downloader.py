# -*- coding: utf-8 -*-
"""
OKX数据下载器和收集器

支持 Parquet 格式本地存储，提供更高的压缩率和查询性能。
"""
from pathlib import Path
from typing import Optional, Union

import pandas as pd
import requests
import warnings
from utils.logger import get_logger, LogType
from utils.timestamp_utils import normalize_to_nanoseconds
from utils.parquet_utils import append_to_parquet

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)
from exchange.base import BaseCollector
from utils.decorators import deco_retry
from utils.deprecation import deprecated


class OKXDownloader(BaseCollector):
    """
    OKX数据下载器和收集器
    
    用于从OKX交易所下载K线数据，并提供数据收集功能。
    """

    def __init__(
        self,
        save_dir: Union[str, Path],
        candle_type='spot',
        start=None,
        end=None,
        interval="1d",
        max_workers=1,
        max_collector_count=2,
        delay=0,
        check_data_length: Optional[int] = None,
        limit_nums: Optional[int] = None,
        symbols=None,
        mode='inc',
    ):
        """
        初始化OKX数据下载器和收集器

        :param save_dir: 数据保存目录
        :param candle_type: 蜡烛图类型，可选'spot'（现货）、'futures'（期货）或'option'（期权）
        :param start: 开始时间
        :param end: 结束时间
        :param interval: 时间间隔，如'1m', '1h', '1d'等
        :param max_workers: 最大工作线程数
        :param max_collector_count: 最大收集次数
        :param delay: 请求延迟时间（秒）
        :param check_data_length: 数据长度检查阈值
        :param limit_nums: 限制收集的标的数量，用于调试
        :param symbols: 交易对列表，如['BTC-USDT', 'ETH-USDT']，如果为None则获取全量交易对
        :param mode: 下载模式，可选'inc'（增量）或'full'（全量），默认'inc'
        """
        super().__init__(
            save_dir=save_dir,
            start=start,
            end=end,
            interval=interval,
            max_workers=max_workers,
            max_collector_count=max_collector_count,
            delay=delay,
            check_data_length=check_data_length,
            limit_nums=limit_nums,
            mode=mode,
        )

        self.candle_type = candle_type
        self.symbols = symbols
        self.base_url = 'https://www.okx.com/api/v5/market'

    @property
    def _timezone(self):
        """获取时区"""
        return "UTC"

    def download(self, symbol, interval, start_date, end_date):
        """
        下载指定交易对的K线数据

        :param symbol: 交易对符号，如'BTC-USDT'
        :param interval: 时间间隔，如'1m', '1h', '1d'等
        :param start_date: 开始日期，格式为'YYYY-MM-DD'
        :param end_date: 结束日期，格式为'YYYY-MM-DD'
        :return: K线数据DataFrame
        """
        try:
            start_ts = int(pd.Timestamp(start_date).timestamp() * 1000)
            end_ts = int(pd.Timestamp(end_date).timestamp() * 1000)

            params = {
                'instId': symbol,
                'bar': interval,
                'after': str(start_ts),
                'before': str(end_ts),
                'limit': '100'
            }

            response = requests.get(f'{self.base_url}/candles', params=params)
            response.raise_for_status()

            data = response.json()['data']

            if not data:
                return pd.DataFrame()

            df = pd.DataFrame(
                data,
                columns=['open_time', 'open', 'high', 'low', 'close', 'volume', 'volume_currency', 'unknown']
            )

            df['open_time'] = pd.to_numeric(df['open_time'])
            df['open'] = pd.to_numeric(df['open'])
            df['high'] = pd.to_numeric(df['high'])
            df['low'] = pd.to_numeric(df['low'])
            df['close'] = pd.to_numeric(df['close'])
            df['volume'] = pd.to_numeric(df['volume'])

            df = df.sort_values('open_time')

            # 统一转换为纳秒级时间戳 (OKX返回的是毫秒级)
            df['open_time'] = df['open_time'].apply(
                lambda x: normalize_to_nanoseconds(x, input_precision='ms')
            )

            return df

        except Exception as e:
            logger.error(f"下载OKX数据失败: {e}")
            return pd.DataFrame()

    def save_data(self, df, save_path):
        """
        保存数据到Parquet文件

        :param df: 要保存的数据DataFrame
        :param save_path: 保存路径（会自动转换为 .parquet 后缀）
        """
        try:
            save_path = Path(save_path)
            # 自动转换为 .parquet 后缀
            if save_path.suffix == '.csv':
                save_path = save_path.with_suffix('.parquet')

            # 使用 append_to_parquet 支持增量更新
            success = append_to_parquet(df, save_path)
            if success:
                logger.info(f"数据已保存到: {save_path} (Parquet 格式)")
            else:
                logger.error(f"保存数据失败: {save_path}")
        except Exception as e:
            logger.error(f"保存数据失败: {e}")

    def _simple_collector(self, symbol: str, progress_callback=None):
        """简单收集器，使用 Parquet 格式保存"""
        self.sleep()

        normalized_symbol = self.normalize_symbol(symbol)
        # 使用 .parquet 后缀
        instrument_path = self.save_dir.joinpath(f"{normalized_symbol}.parquet")

        existing_timestamps = pd.Series([], dtype='int64')
        if self.mode == 'inc' and instrument_path.exists():
            try:
                _old_df = pd.read_parquet(instrument_path)
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
            df = self.download(symbol, self.interval, range_start.strftime("%Y-%m-%d"), range_end.strftime("%Y-%m-%d"), progress_callback)
            if df is not None and not df.empty:
                all_df = pd.concat([all_df, df], ignore_index=True)

        if all_df.empty:
            logger.warning(f"{symbol} 下载数据为空")
            return self.NORMAL_FLAG

        result = self.cache_small_data(symbol, all_df)
        if result != self.NORMAL_FLAG:
            return result

        self.save_instrument(symbol, all_df)

        return self.NORMAL_FLAG

    def save_instrument(self, symbol, df: pd.DataFrame):
        """保存标的数据到 Parquet 文件"""
        if df is None or df.empty:
            logger.warning(f"{symbol} 数据为空")
            return

        symbol = self.normalize_symbol(symbol)
        # 直接使用 save_dir（已经是完整的目标目录: .../crypto/spot/klines/{interval}）
        # 只需拼接文件名，不再重复拼接路径结构
        instrument_path = self.save_dir / f"{symbol}.parquet"
        # 最终路径: {save_dir}/{symbol}.parquet
        # 例如: backend/data/source/crypto/spot/klines/15m/BTCUSDT.parquet ✅
        df["symbol"] = symbol

        # 统一列名：确保存在 timestamp 列（兼容 date 列名）
        if 'date' in df.columns and 'timestamp' not in df.columns:
            df = df.rename(columns={'date': 'timestamp'})
        if 'timestamp' not in df.columns:
            logger.error(f"{symbol} 数据缺少 timestamp/date 列，可用列: {list(df.columns)}")
            return
        df['timestamp'] = pd.to_numeric(df['timestamp'], errors='coerce')
        df = df.dropna(subset=['timestamp'])
        df = df.drop_duplicates(subset=['timestamp'], keep='last')
        df = df.sort_values('timestamp')

        if self.mode != 'full' and instrument_path.exists():
            try:
                _old_df = pd.read_parquet(instrument_path)
                if 'date' in _old_df.columns and 'timestamp' not in _old_df.columns:
                    _old_df = _old_df.rename(columns={'date': 'timestamp'})
                _old_df['timestamp'] = pd.to_numeric(_old_df['timestamp'], errors='coerce')
                df = pd.concat([_old_df, df], sort=False)
                df = df.drop_duplicates(subset=['timestamp'], keep='last')
                df = df.sort_values('timestamp')
            except Exception as e:
                logger.warning(f"读取现有 parquet 文件失败，将覆盖: {e}")

        # 使用 append_to_parquet 保存
        self.save_data(df, instrument_path)

        mode_label = "[全量模式]" if self.mode == "full" else "[增量模式]"
        logger.info(f"{mode_label} 成功将 {symbol} 数据保存到文件: {instrument_path}")

    @deco_retry(max_retry=3, delay=1.0)
    def get_all_symbols(self):
        """
        从OKX API获取全量交易对列表

        :return: 交易对列表
        """
        try:
            if self.candle_type == 'spot':
                url = 'https://www.okx.com/api/v5/public/instruments'
                params = {'instType': 'SPOT'}
            elif self.candle_type == 'futures':
                url = 'https://www.okx.com/api/v5/public/instruments'
                params = {'instType': 'SWAP'}
            else:
                logger.warning(f"暂不支持获取{self.candle_type}类型的交易对列表")
                return []

            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            symbols = [symbol['instId'] for symbol in data['data'] if symbol['state'] == 'live']
            logger.info(f"成功获取{len(symbols)}个{self.candle_type}交易对")
            return symbols
        except Exception as e:
            logger.error(f"获取交易对列表失败: {e}")
            return []

    def get_instrument_list(self):
        """
        获取OKX交易对列表

        :return: 交易对列表
        """
        if hasattr(self, 'symbols') and self.symbols:
            return self.symbols

        return self.get_all_symbols()

    def normalize_symbol(self, symbol):
        """
        标准化交易对符号

        :param symbol: 交易对符号，如'BTC/USDT'或'BTC-USDT'
        :return: 标准化后的交易对符号，如'BTCUSDT'
        """
        return symbol.replace('/', '').replace('-', '')

    def get_data(
        self, symbol: str, interval: str, start_datetime: pd.Timestamp, end_datetime: pd.Timestamp, progress_callback=None
    ) -> pd.DataFrame:
        """
        获取指定交易对的K线数据

        :param symbol: 交易对符号
        :param interval: 时间间隔
        :param start_datetime: 开始时间
        :param end_datetime: 结束时间
        :return: K线数据DataFrame
        """
        try:
            start_date = start_datetime.strftime('%Y-%m-%d')
            end_date = end_datetime.strftime('%Y-%m-%d')

            logger.info(f"开始下载 {symbol} {interval} 数据，时间范围: {start_date} 至 {end_date}")

            df = self.download(symbol, interval, start_date, end_date)

            if df.empty:
                logger.warning(f"{symbol} {interval} 数据为空")
                return df

            df['timestamp'] = df['open_time']
            df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
            df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']

            start_timestamp = int(start_datetime.timestamp() * 1000)
            end_timestamp = int(end_datetime.timestamp() * 1000)
            df = df[(df['timestamp'] >= start_timestamp) & (df['timestamp'] <= end_timestamp)]

            logger.info(f"成功下载 {symbol} {interval} 数据，共 {len(df)} 条")
            return df
        except Exception as e:
            logger.error(f"下载 {symbol} {interval} 数据失败: {e}")
            return pd.DataFrame()

    def download_from_archive(self, symbol, timeframe, start_date, end_date):
        """
        从OKX下载历史数据

        :param symbol: 交易对符号
        :param timeframe: 时间间隔
        :param start_date: 开始日期，格式为'YYYY-MM-DD'
        :param end_date: 结束日期，格式为'YYYY-MM-DD'
        :return: 下载的数据量
        """
        df = self.download(symbol, timeframe, start_date, end_date)
        if not df.empty:
            # 使用 .parquet 后缀保存
            save_path = self.save_dir / f"{symbol}.parquet"
            self.save_data(df, save_path)
            return len(df)
        return 0

    @deprecated("2.1", "3.0", "scripts/data_cli.py export csv/parquet")
    def convert_to_qlib(self, csv_dir, qlib_dir, interval=None):
        """
        将下载的CSV数据转换为QLib格式

        .. deprecated:: 2.1
            此功能已弃用，QLib转换不再支持。
            如需数据格式转换，请使用 scripts/data_cli.py 的导出功能。

        :param csv_dir: CSV数据目录
        :param qlib_dir: QLib数据保存目录
        :param interval: 时间间隔，如'1m', '1h', '1d'等，如果为None则使用当前收集器的interval
        :return: False (功能已禁用)
        """
        logger.warning("QLib格式转换功能已移除")
        logger.info(f"如需数据导出，请使用: python scripts/data_cli.py export csv/parquet ...")
        return False

    def collect_data(self, progress_callback=None):
        """
        执行数据收集

        :param progress_callback: 进度回调函数，格式为 callback(current, completed, total, failed)
        :return: 收集结果
        """
        result = super().collect_data(progress_callback=progress_callback)
        return result


# 向后兼容别名（带弃用警告）
def _okx_collector_init_warning(self, *args, **kwargs):
    """
    .. deprecated:: 2.1
        请使用 OKXDownloader 替代
    """
    warnings.warn(
        "OKXCollector 类名已弃用（v2.1），请使用 OKXDownloader",
        DeprecationWarning,
        stacklevel=2
    )
    OKXDownloader.__init__(self, *args, **kwargs)

OKXCollector = type('OKXCollector', (OKXDownloader,), {
    '__module__': 'exchange.okx.downloader',
    '__doc__': '.. deprecated:: 2.1\n\n    请使用 :class:`OKXDownloader` 替代',
    '__init__': _okx_collector_init_warning
})

__all__ = ["OKXDownloader", "OKXCollector"]
