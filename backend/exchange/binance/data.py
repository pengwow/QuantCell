# coding=utf-8
import time
from multiprocessing import Process, Queue
import os
from datetime import datetime, timedelta
import zipfile
from numpy.random import f
import pandas as pd
import numpy as np
import aiohttp
import asyncio
import ccxt
from tqdm import tqdm
from io import BytesIO
import ssl
import certifi
# 延迟导入以避免循环依赖
from zbot.utils.dateutils import get_date_range, str_to_timestamp
from zbot.exchange.binance.models import Candle


class History(object):
    def __init__(self, exchange):
        self.exchange = exchange.exchange
        self.candle_names = exchange.candle_names

        self.exchange.parse_ohlcv = self.prase_ohlcv_custom

    def prase_ohlcv_custom(self, ohlcv, market):
        # 获取原始OHLCV响应
        return ohlcv

    @staticmethod
    def get_interval_minutes(interval):
        """
        静态方法，用于获取时间间隔对应的分钟数
        :param interval: 时间间隔，如 '1m', '1h' 等
        :return: 时间间隔对应的分钟数，如果未找到则返回 1
        """
        # 定义时间间隔与分钟数的映射关系
        interval_map = {
            '1m': 1,
            '3m': 3,
            '5m': 5,
            '15m': 15,
            '30m': 30,
            '1h': 60,
            '2h': 120,
            '4h': 240,
            '6h': 360,
            '8h': 480,
            '12h': 720,
            '1d': 1440,
            '3d': 4320,
            '1w': 10080,
            '1M': 43200
        }
        # 根据时间间隔获取对应的分钟数，未找到则返回 1
        return interval_map.get(interval, 1)

    @staticmethod
    def format_candle(candle: list, data_source: str = 'unknown') -> dict:
        return dict(
            open_time=candle[0],
            open=candle[1],
            high=candle[2],
            low=candle[3],
            close=candle[4],
            volume=candle[5],
            close_time=candle[6],
            quote_volume=candle[7],
            count=candle[8],
            taker_buy_volume=candle[9],
            taker_buy_quote_volume=candle[10],
            ignore=candle[11],
            data_source=data_source
        )

    def load_and_clean_data(self, symbol: str, timeframe: str, start_time=None, end_time=None) -> pd.DataFrame:
        """
        从数据库读取K线数据并加载到DataFrame，执行数据清理操作
        :param symbol: 货币对
        :param timeframe: 时间间隔
        :param start_time: 开始时间（字符串或时间戳）
        :param end_time: 结束时间（字符串或时间戳）
        :return: 清理后的DataFrame
        """
        # 处理时间参数
        # 查询数据库
        start = str_to_timestamp(start_time, 'us')
        end = str_to_timestamp(end_time, 'us')
        # 查询指定条件的K线数据并按时间戳排序
        candles = list(
            Candle.select().where(
                (Candle.symbol == symbol)
                & (Candle.timeframe == timeframe)
                & Candle.open_time.between(start, end)
            ).order_by(Candle.open_time)
        )

        # 转换为DataFrame
        df = pd.DataFrame([candle.__data__ for candle in candles])

        if df.empty:
            return df

        # 数据清理
        # 1. 去除重复数据
        df = df.drop_duplicates(subset=['open_time'], keep='last')

        # 2. 检查并处理缺失值
        df = df.dropna()

        # 3. 确保时间序列连续
        expected_interval = self._get_interval_ms(timeframe) * 1000  # 转换为微秒
        all_timestamps = pd.date_range(
            start=pd.to_datetime(df['open_time'].min(), unit='us'),
            end=pd.to_datetime(df['open_time'].max(), unit='us'),
            freq=f'{expected_interval//1000000}S'  # 转换回秒用于设置频率
        ).astype(np.int64)  # 转换为微秒级时间戳

        # 找出缺失的时间戳
        existing_timestamps = set(df['open_time'])
        missing_timestamps = [
            ts for ts in all_timestamps if ts not in existing_timestamps]

        if missing_timestamps:
            print(f"警告: 检测到{len(missing_timestamps)}个缺失的K线数据点")

        # 转换列名为大写以兼容Backtesting.py
        df = df.rename(columns={
            'open': 'Open',
            'high': 'High',
            'low': 'Low',
            'close': 'Close',
            'volume': 'Volume'
        })

        # 设置datetime索引
        df['datetime'] = pd.to_datetime(df['open_time'], unit='ms')
        df.set_index('datetime', inplace=True)

        return df

    def download_data(self, symbol, interval, start_time=None, end_time=None, limit=500):
        # TODO: 未完,根据fetch_ohlcv返回结果,进行遍历,只取所有符合要求的 start_time 和 end_time时间戳数据返回
        all_ohlcv = []
        ohlcv = self.exchange.fetch_ohlcv(
            symbol, interval, None, limit, params={})
        all_ohlcv.extend(ohlcv)
        self._process_ohlcv_data(symbol, interval, ohlcv)
        # 查询数据库中已存在的K线时间戳
        existing_times = set()
        from zbot.exchange.binance.models import Candle
        if Candle.table_exists():
            # 确保数据库连接已打开
            from zbot.services.db import database
            database.open_connection()

            # 查询该交易对和时间间隔下的所有已有记录
            existing_records = Candle.select(Candle.open_time).where(
                (Candle.symbol == symbol) &
                (Candle.timeframe == interval)
            )
            existing_times = {record.open_time for record in existing_records}

        bulk_create = []
        bulk_update = []

        # 遍历获取到的K线数据
        for candle_data in ohlcv:
            formatted_data = self.format_candle(candle_data, data_source='ccxt_binance')
            open_time = formatted_data['open_time']

            # 检查记录是否已存在
            if open_time in existing_times:
                # 准备更新数据
                bulk_update.append({
                    'symbol': symbol,
                    'timeframe': interval,
                    'open_time': open_time,
                    'open': formatted_data['open'],
                    'high': formatted_data['high'],
                    'low': formatted_data['low'],
                    'close': formatted_data['close'],
                    'volume': formatted_data['volume'],
                    'close_time': formatted_data['close_time'],
                    'quote_volume': formatted_data['quote_volume'],
                    'data_source': formatted_data['data_source'],
                })
            else:
                # 准备创建新记录
                bulk_create.append(
                    Candle(symbol=symbol, timeframe=interval, **formatted_data)
                )

        # 执行批量操作
        if bulk_create:
            Candle.bulk_create(bulk_create)
            print(f"Created {len(bulk_create)} new candle records")

        if bulk_update:
            # 使用peewee的批量更新方式
            from peewee import Case
            update_query = Candle.update(
                open=Case(Candle.open_time, [
                          (item['open_time'], item['open']) for item in bulk_update]),
                high=Case(Candle.open_time, [
                          (item['open_time'], item['high']) for item in bulk_update]),
                low=Case(Candle.open_time, [
                         (item['open_time'], item['low']) for item in bulk_update]),
                close=Case(Candle.open_time, [
                           (item['open_time'], item['close']) for item in bulk_update]),
                volume=Case(Candle.open_time, [
                            (item['open_time'], item['volume']) for item in bulk_update]),
                close_time=Case(Candle.open_time, [
                                (item['open_time'], item['close_time']) for item in bulk_update]),
                quote_volume=Case(Candle.open_time, [
                                  (item['open_time'], item['quote_volume']) for item in bulk_update])
            ).where(
                (Candle.symbol == symbol) &
                (Candle.timeframe == interval) &
                (Candle.open_time << [item['open_time']
                 for item in bulk_update])
            )
            update_count = update_query.execute()
            print(f"Updated {update_count} existing candle records")

        return all_ohlcv

    def _get_interval_ms(self, interval):
        """将时间间隔字符串转换为毫秒数"""
        interval_map = {
            '1m': 60 * 1000,
            '5m': 5 * 60 * 1000,
            '15m': 15 * 60 * 1000,
            '30m': 30 * 60 * 1000,
            '1h': 60 * 60 * 1000,
            '4h': 4 * 60 * 60 * 1000,
            '1d': 24 * 60 * 60 * 1000,
        }
        return interval_map.get(interval, 60 * 1000)  # 默认1分钟

    def _process_ohlcv_data(self, symbol, interval, ohlcv):
        """
        处理获取到的 K 线数据，插入或更新到数据库
        :param symbol: 货币对
        :param interval: 时间间隔
        :param ohlcv: K 线数据列表
        """
        for candle in ohlcv:
            candle_data = self.format_candle(candle, data_source='ccxt_binance')
            # 根据 symbol、open_time 和 interval 查询是否已存在记录
            from zbot.exchange.binance.models import Candle
            existing_candle = Candle.select().where(
                (Candle.symbol == symbol) &
                (Candle.timeframe == interval) &
                (Candle.open_time == candle_data['open_time'])
            ).first()
            if existing_candle:
                # 如果存在则更新记录
                for key, value in candle_data.items():
                    setattr(existing_candle, key, value)
                existing_candle.save()
            else:
                # 如果不存在则创建新记录
                Candle.create(
                    symbol=symbol,
                    timeframe=interval,
                    **candle_data
                )

    def download_from_archive(self, symbol, timeframe, candle_type, start_date, end_date, progress_queue=None):
        from zbot.exchange.binance.models import Candle
        date_range = get_date_range(start_date, end_date)
        total = len(date_range)
        for i, date in enumerate(tqdm(date_range, desc=f"Downloading {symbol} {timeframe} data", total=total)):
            res = asyncio.run(self.get_daily_klines(
                symbol, timeframe, candle_type, date))
            if res is not None and not res.empty:
                bulk_data = []
                for _, row in res.iterrows():
                    candle_data = row.to_dict()
                    # 设置数据来源为binance_csv
                    candle_data['data_source'] = 'binance_csv'
                    # 根据 symbol、open_time 和 timeframe 查询是否已存在记录
                    existing_candle = Candle.select().where(
                        (Candle.symbol == symbol) &
                        (Candle.timeframe == timeframe) &
                        (Candle.open_time == candle_data['open_time'])
                    ).first()
                    if existing_candle:
                        # 如果存在则更新记录
                        for key, value in candle_data.items():
                            setattr(existing_candle, key, value)
                        existing_candle.save()
                    else:
                        # 如果不存在则创建新记录
                        bulk_data.append(
                            Candle(
                                symbol=symbol,
                                timeframe=timeframe,
                                **candle_data
                            )
                        )

                if bulk_data:
                    Candle.bulk_create(bulk_data)
            if progress_queue:
                # progress_queue.put((i + 1, total))  # 发送当前进度和总数
                progress_queue.put(
                    {'symbol': symbol, 'date': date, 'progress': (i + 1) / total})
        if progress_queue:
            progress_queue.put(None)  # 发送完成信号
        return date_range

    @staticmethod
    def get_url_by_candle_type(candle_type):
        if candle_type in ('spot', 'option'):
            return candle_type
        elif candle_type == 'futures':
            return 'futures/um'
        else:
            raise ValueError('Invalid candle_type')

    def get_zip_name(self, symbol, timeframe, date):
        return f"{symbol}-{timeframe}-{date}.zip"

    def get_zip_url(self, symbol, timeframe, candle_type, date):
        """
        获取压缩文件下载地址
        https://data.binance.vision/data/spot/daily/klines/BTCUSDT/5m/BTCUSDT-5m-2024-10-27.zip
        https://data.binance.vision/data/futures/um/daily/klines/BTCUSDT/1h/BTCUSDT-1h-2024-10-27.zip
        :param symbol: 货币对
        :param timeframe: 时间间隔
        :param candle_type: 类型
        :param date: 日期
        :return:
        """
        symbol = symbol.replace('/', '')
        asset_type = self.get_url_by_candle_type(candle_type)
        zip_name = self.get_zip_name(symbol, timeframe, date)
        url = (
            f"https://data.binance.vision/data/{
                asset_type}/daily/klines/{symbol}"
            f"/{timeframe}/{zip_name}"
        )
        return url

    # 异步获取指定日期的K线数据
    async def get_daily_klines(self, symbol, timeframe, candle_type, date):
        url = self.get_zip_url(symbol, timeframe, candle_type, date)
        connector = aiohttp.TCPConnector(
            ssl=ssl.create_default_context(cafile=certifi.where()))
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    content = await resp.read()
                    # logger.debug(f"Successfully downloaded {url}")
                    with zipfile.ZipFile(BytesIO(content)) as zipf:
                        with zipf.open(zipf.namelist()[0]) as csvf:
                            # https://github.com/binance/binance-public-data/issues/283
                            first_byte = csvf.read(1)[0]
                            if chr(first_byte).isdigit():
                                header = None
                            else:
                                header = 0
                            csvf.seek(0)

                            df = pd.read_csv(
                                csvf,
                                usecols=[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],
                                names=self.candle_names,
                                header=header
                            )
                            # df["open_time"] = pd.to_datetime(
                            #     np.where(df["open_time"] > 1e13, df["open_time"] // 1000, df["open_time"]),
                            #     unit="ms",
                            #     utc=True,
                            # )
                            return df
        return None


def monitor_progress(queue, total):
    """监控进度的独立进程"""
    from tqdm import tqdm
    pbar = tqdm(total=total, desc="整体下载进度")
    while True:
        item = queue.get()
        if item is None:  # 收到结束信号
            break
        current, total = item
        pbar.update(current - pbar.n)  # 更新进度条
    pbar.close()


if __name__ == '__main__':
    from zbot.common.config import read_config
    config = read_config('BINANCE')
    # exchange = ccxt.binance({
    #         'apiKey': config.get('api_key'),
    #         'secret': config.get('secret_key'),
    #         'enableRateLimit': True,
    #         'options': {'defaultType': 'spot'},
    # })
    # exchange.fetch_ohlcv()
    # exchange.proxies = {
    #     'https': config.get('proxy_url'),
    #     'http': config.get('proxy_url')
    # }
    from zbot.exchange.binance.connector import BinanceExchange
    exchange = BinanceExchange(**{
        'api_key': config.get('api_key'),
        'secret_key': config.get('secret_key'),
        'proxy_url': config.get('proxy_url')
    })
    h = History(exchange)
    # h.download_data('BTC/USDT', '15m')
    h.download_data('BTCUSDT', '15m', '')
    # h.download_from_archive('BTCUSDT', '15m', 'futures', '2024-10-27')
    # res = h.get_zip_url('BTCUSDT', '15m', 'spot', '2024-10-27')
    # print(res)
    # 示例：使用多进程下载并监控进度
    start_date = '2024-10-27'
    end_date = '2024-10-28'

    # 创建进度队列
    progress_queue = Queue()

    # 获取日期范围计算总数
    date_range = get_date_range(start_date, end_date)
    total_dates = len(date_range)

    # 启动下载进程
    download_process = Process(
        target=h.download_from_archive,
        args=('BTCUSDT', '15m', 'futures', start_date, end_date),
        kwargs={'progress_queue': progress_queue}
    )
    download_process.start()

    # 启动进度监控进程
    monitor_process = Process(
        target=monitor_progress,
        args=(progress_queue, total_dates)
    )
    monitor_process.start()

    # 等待完成
    download_process.join()
    monitor_process.join()
    print("下载完成!")

    # h.load_and_clean_data('BTCUSDT', '15m','2024-10-27','2024-10-28')
