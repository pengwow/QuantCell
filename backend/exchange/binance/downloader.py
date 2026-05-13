# -*- coding: utf-8 -*-
"""
币安数据下载器和收集器

支持 Parquet 格式本地存储，提供更高的压缩率和查询性能。
"""
import asyncio
import ssl
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Optional, Union

import aiohttp
import certifi
import pandas as pd
import requests
from utils.logger import get_logger, LogType
from utils.timestamp_utils import normalize_to_nanoseconds
from utils.parquet_utils import save_to_parquet, append_to_parquet

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)
from exchange.base import BaseCollector
from utils.decorators import async_deco_retry, deco_retry
from utils.time_parser import get_date_range


class BinanceDownloader(BaseCollector):
    """
    币安数据下载器和收集器
    
    用于从Binance API和Binance Data Archive下载K线数据，
    并提供数据收集功能。
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
        初始化币安数据下载器和收集器

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
        :param symbols: 交易对列表，如['BTCUSDT', 'ETHUSDT']，如果为None则获取全量交易对
        :param mode: 下载模式，可选'inc'（增量）或'full'（全量），默认'inc'
        """
        # 先设置 candle_type 和 symbols，因为父类初始化会调用 get_instrument_list()
        self.candle_type = candle_type
        self.symbols = symbols
        
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

        self.candle_names = [
            'open_time', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_volume', 'count', 'taker_buy_volume',
            'taker_buy_quote_volume', 'ignore'
        ]

    @property
    def _timezone(self):
        """获取时区"""
        return "UTC"

    @staticmethod
    def get_url_by_candle_type(candle_type):
        """
        根据蜡烛图类型获取对应的URL路径

        :param candle_type: 蜡烛图类型，可选'spot'（现货）、'futures'（永续合约）、'futures/um'（U本位永续合约）、'futures/cm'（币本位永续合约）或'option'（期权）
        :return: URL路径
        """
        url_map = {
            'spot': 'spot',
            'option': 'option',
            'futures': 'futures/um',
            'futures/um': 'futures/um',
            'futures/cm': 'futures/cm',
        }

        if candle_type in url_map:
            return url_map[candle_type]
        else:
            raise ValueError(f'无效的蜡烛图类型: {candle_type}')

    def get_zip_name(self, symbol, timeframe, date):
        """
        获取压缩文件名称

        :param symbol: 交易对，如'BTCUSDT'
        :param timeframe: 时间间隔，如'1m'、'1h'、'1d'等
        :param date: 日期，格式为'YYYY-MM-DD'
        :return: 压缩文件名称
        """
        return f"{symbol}-{timeframe}-{date}.zip"

    def get_zip_url(self, symbol, timeframe, date):
        """
        获取压缩文件下载地址

        :param symbol: 交易对，如'BTCUSDT'
        :param timeframe: 时间间隔，如'1m'、'1h'、'1d'等
        :param date: 日期，格式为'YYYY-MM-DD'
        :return: 压缩文件下载URL
        """
        symbol = symbol.replace('/', '')
        asset_type = self.get_url_by_candle_type(self.candle_type)
        zip_name = self.get_zip_name(symbol, timeframe, date)
        url = (
            f"https://data.binance.vision/data/{asset_type}/daily/klines/{symbol}"
            f"/{timeframe}/{zip_name}"
        )
        return url

    @async_deco_retry(max_retry=3, delay=1.0)
    async def get_daily_klines(self, symbol, timeframe, date):
        """
        异步获取指定日期的K线数据

        :param symbol: 交易对，如'BTCUSDT'
        :param timeframe: 时间间隔，如'1m'、'1h'、'1d'等
        :param date: 日期，格式为'YYYY-MM-DD'
        :return: K线数据DataFrame
        """
        url = self.get_zip_url(symbol, timeframe, date)
        connector = aiohttp.TCPConnector(
            ssl=ssl.create_default_context(cafile=certifi.where())
        )

        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    content = await resp.read()
                    logger.debug(f"成功下载 {url}")

                    with zipfile.ZipFile(BytesIO(content)) as zipf:
                        filename = zipf.namelist()[0]
                        with zipf.open(filename) as csvf:
                            csv_content = BytesIO(csvf.read())
                            csv_content.seek(0)

                            first_line = csv_content.readline().decode('utf-8')
                            csv_content.seek(0)

                            has_header = not first_line.strip()[0].isdigit()
                            header = 0 if has_header else None

                            df = pd.read_csv(
                                csv_content,
                                names=self.candle_names,
                                header=header
                            )

                            df.columns = self.candle_names

                            logger.info(f"成功处理 {symbol} {timeframe} 数据 ({date}): 共 {len(df)} 条记录, 文件: {filename}, 表头: {'有' if has_header else '无'}")
                            return df
                else:
                    logger.warning(f"下载失败 {url}，状态码: {resp.status}")
                    return None

    async def download_daily_klines(self, symbol, timeframe, start_date, end_date, progress_callback=None):
        """
        异步下载指定日期范围内的K线数据

        :param symbol: 交易对，如'BTCUSDT'
        :param timeframe: 时间间隔，如'1m'、'1h'、'1d'等
        :param start_date: 开始日期，格式为'YYYY-MM-DD'
        :param end_date: 结束日期，格式为'YYYY-MM-DD'
        :param progress_callback: 进度回调函数，格式为 callback(symbol, current, total, status)
        :return: K线数据DataFrame
        """
        date_range = get_date_range(start_date, end_date)
        all_data = []
        total_dates = len(date_range)

        for idx, date in enumerate(date_range):
            df = await self.get_daily_klines(symbol, timeframe, date)
            if df is not None and not df.empty:
                all_data.append(df)

            if progress_callback:
                progress_callback(symbol, idx + 1, total_dates, f"Downloaded {date}")

        if all_data:
            return pd.concat(all_data, ignore_index=True)
        else:
            return pd.DataFrame()

    def download(self, symbol, timeframe, start_date, end_date, progress_callback=None):
        """
        下载指定日期范围内的K线数据（同步接口）

        :param symbol: 交易对，如'BTCUSDT'
        :param timeframe: 时间间隔，如'1m'、'1h'、'1d'等
        :param start_date: 开始日期，格式为'YYYY-MM-DD'
        :param end_date: 结束日期，格式为'YYYY-MM-DD'
        :param progress_callback: 进度回调函数，格式为 callback(symbol, current, total, status)
        :return: K线数据DataFrame
        """
        return asyncio.run(self.download_daily_klines(symbol, timeframe, start_date, end_date, progress_callback))

    def save_data(self, df, save_path):
        """
        保存K线数据到文件（Parquet格式）

        :param df: K线数据DataFrame
        :param save_path: 保存路径（会自动转换为 .parquet 后缀）
        """
        if df is not None and not df.empty:
            save_path = Path(save_path)
            # 自动转换为 .parquet 后缀
            if save_path.suffix == '.csv':
                save_path = save_path.with_suffix('.parquet')

            # 使用 append_to_parquet 支持增量更新
            success = append_to_parquet(df, save_path)
            if success:
                logger.info(f"数据已保存到 {save_path} (Parquet 格式)")
            else:
                logger.error(f"保存数据失败: {save_path}")
        else:
            logger.warning(f"数据为空，未保存到 {save_path}")

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

        # 统一列名：确保存在 timestamp 列（兼容 date/open_time 列名）
        if 'date' in df.columns and 'timestamp' not in df.columns:
            df = df.rename(columns={'date': 'timestamp'})
        if 'open_time' in df.columns and 'timestamp' not in df.columns:
            df = df.rename(columns={'open_time': 'timestamp'})
        if 'timestamp' not in df.columns:
            logger.error(f"{symbol} 数据缺少 timestamp/date/open_time 列，可用列: {list(df.columns)}")
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
        从Binance API获取全量交易对列表

        :return: 交易对列表
        """
        try:
            if self.candle_type == 'spot':
                url = 'https://api.binance.com/api/v3/exchangeInfo'
            elif self.candle_type == 'futures':
                url = 'https://fapi.binance.com/fapi/v1/exchangeInfo'
            else:
                logger.warning(f"暂不支持获取{self.candle_type}类型的交易对列表")
                return []

            response = requests.get(url)
            response.raise_for_status()
            data = response.json()

            symbols = [symbol['symbol'] for symbol in data['symbols'] if symbol['status'] == 'TRADING']
            logger.info(f"成功获取{len(symbols)}个{self.candle_type}交易对")
            return symbols
        except Exception as e:
            logger.error(f"获取交易对列表失败: {e}")
            return []

    def get_instrument_list(self):
        """
        获取币安交易对列表

        :return: 交易对列表
        """
        if hasattr(self, 'symbols'):
            if self.symbols is None:
                return self.get_all_symbols()
            elif isinstance(self.symbols, (list, tuple)) and len(self.symbols) == 0:
                return []
            else:
                return self.symbols

        return self.get_all_symbols()

    def normalize_symbol(self, symbol):
        """
        标准化交易对符号

        :param symbol: 交易对符号，如'BTC/USDT'或'BTCUSDT'
        :return: 标准化后的交易对符号，如'BTCUSDT'
        """
        return symbol.replace('/', '')

    def get_data(
        self, symbol: str, interval: str, start_datetime: pd.Timestamp, end_datetime: pd.Timestamp, progress_callback=None
    ) -> pd.DataFrame:
        """
        获取指定交易对的K线数据

        :param symbol: 交易对符号
        :param interval: 时间间隔
        :param start_datetime: 开始时间
        :param end_datetime: 结束时间
        :param progress_callback: 进度回调函数，格式为 callback(symbol, current, total, status)
        :return: K线数据DataFrame
        """
        try:
            start_date = start_datetime.strftime('%Y-%m-%d')
            end_date = end_datetime.strftime('%Y-%m-%d')

            logger.info(f"开始下载 {symbol} {interval} 数据，时间范围: {start_date} 至 {end_date}")

            df = self.download(symbol, interval, start_date, end_date, progress_callback)

            if df.empty:
                logger.warning(f"{symbol} {interval} 数据为空")
                return pd.DataFrame()

            logger.info(f"原始数据行数: {len(df)}")

            df['open_time'] = pd.to_numeric(df['open_time'], errors='coerce')
            df = df.dropna(subset=['open_time'])

            if df.empty:
                logger.warning(f"{symbol} {interval} 数据在转换为数值类型后为空")
                return pd.DataFrame()

            filtered_df = df.loc[:, ['open_time', 'open', 'high', 'low', 'close', 'volume']]
            filtered_df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']

            # 统一转换为纳秒级时间戳
            if not filtered_df.empty:
                # 根据时间戳长度判断精度并转换为纳秒级
                def convert_to_nanoseconds(ts):
                    ts_str = str(int(ts))
                    if len(ts_str) > 18:  # 已经是纳秒级
                        return int(ts)
                    elif len(ts_str) > 15:  # 微秒级
                        return int(ts) * 1_000
                    elif len(ts_str) > 12:  # 毫秒级
                        return int(ts) * 1_000_000
                    else:  # 秒级
                        return int(ts) * 1_000_000_000
                
                filtered_df['timestamp'] = filtered_df['timestamp'].apply(convert_to_nanoseconds)

            # 时间范围筛选使用纳秒级时间戳
            start_ts_ns = int(start_datetime.timestamp() * 1_000_000_000)
            end_ts_ns = int(end_datetime.timestamp() * 1_000_000_000)
            filtered_df = filtered_df[(filtered_df['timestamp'] >= start_ts_ns) & (filtered_df['timestamp'] <= end_ts_ns)]

            logger.info(f"成功下载 {symbol} {interval} 数据，共 {len(filtered_df)} 条")

            return filtered_df
        except Exception as e:
            logger.error(f"下载 {symbol} {interval} 数据失败: {e}")
            logger.exception(e)
            return pd.DataFrame()

    def download_from_archive(self, symbol, timeframe, start_date, end_date):
        """
        从Binance Data Archive下载历史数据

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

    def convert_to_qlib(self, csv_dir, qlib_dir, interval=None):
        """
        将下载的CSV数据转换为QLib格式
        
        注意：此功能已弃用，QLib转换不再支持。
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


# 向后兼容别名
BinanceCollector = BinanceDownloader

__all__ = ["BinanceDownloader", "BinanceCollector"]
