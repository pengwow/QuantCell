# OKX数据下载器和收集器
from pathlib import Path
from typing import Optional, Union

import pandas as pd
import requests
from loguru import logger

from common.collectors import BaseCollector
from common.collectors.utils import deco_retry


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

            return df

        except Exception as e:
            logger.error(f"下载OKX数据失败: {e}")
            return pd.DataFrame()

    def save_data(self, df, save_path):
        """
        保存数据到CSV文件

        :param df: 要保存的数据DataFrame
        :param save_path: 保存路径
        """
        try:
            save_path = Path(save_path)
            save_path.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(save_path, index=False)
            logger.info(f"数据已保存到: {save_path}")
        except Exception as e:
            logger.error(f"保存数据失败: {e}")

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
            save_path = self.save_dir / f"{symbol}.csv"
            self.save_data(df, save_path)
            return len(df)
        return 0

    def convert_to_qlib(self, csv_dir, qlib_dir, interval=None):
        """
        将下载的CSV数据转换为QLib格式

        :param csv_dir: CSV数据目录
        :param qlib_dir: QLib数据保存目录
        :param interval: 时间间隔，如'1m', '1h', '1d'等，如果为None则使用当前收集器的interval
        :return: 转换结果
        """
        try:
            from collector.scripts.convert_to_qlib import convert_crypto_to_qlib

            logger.info(f"开始将CSV数据转换为QLib格式...")

            if interval is None:
                interval = self.interval

            qlib_freq = "day" if interval == "1d" else interval

            result = convert_crypto_to_qlib(
                csv_dir=csv_dir,
                qlib_dir=qlib_dir,
                freq=qlib_freq,
                date_field_name="timestamp",
                file_suffix=".csv",
                symbol_field_name="symbol",
                include_fields="timestamp,open,high,low,close,volume",
                max_workers=self.max_workers
            )

            if result:
                logger.info("数据转换完成！")
            else:
                logger.error("数据转换失败！")

            return result
        except Exception as e:
            logger.error(f"数据转换失败: {e}")
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
OKXCollector = OKXDownloader

__all__ = ["OKXDownloader", "OKXCollector"]
