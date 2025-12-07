# 币安数据下载器
import asyncio
import ssl
import zipfile
from io import BytesIO
from pathlib import Path

import aiohttp
import certifi
import pandas as pd
from loguru import logger

from ...base.utils import get_date_range, async_deco_retry


class BinanceDownloader:
    """币安数据下载器，用于从Binance API和Binance Data Archive下载K线数据"""
    
    def __init__(self, candle_type='spot'):
        """
        初始化币安数据下载器
        
        :param candle_type: 蜡烛图类型，可选'spot'（现货）、'futures'（期货）或'option'（期权）
        """
        self.candle_type = candle_type
        self.candle_names = [
            'open_time', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_volume', 'count', 'taker_buy_volume',
            'taker_buy_quote_volume', 'ignore'
        ]
    
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
            'futures': 'futures/um',  # 默认U本位永续合约
            'futures/um': 'futures/um',  # U本位永续合约
            'futures/cm': 'futures/cm',  # 币本位永续合约
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
                            # 检查CSV文件是否有表头
                            first_line = csvf.readline().decode('utf-8')
                            csvf.seek(0)
                            
                            # 判断第一行是否为数字开头（无表头）
                            has_header = not first_line.strip()[0].isdigit()
                            
                            # 根据是否有表头设置header参数
                            header = 0 if has_header else None
                            
                            # 读取CSV文件
                            df = pd.read_csv(
                                csvf,
                                usecols=list(range(12)),
                                names=self.candle_names,
                                header=header
                            )
                            
                            # 确保列名与预期一致
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
            
            # 更新进度
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
        保存K线数据到文件
        
        :param df: K线数据DataFrame
        :param save_path: 保存路径
        """
        if df is not None and not df.empty:
            save_path = Path(save_path)
            save_path.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(save_path, index=False)
            logger.info(f"数据已保存到 {save_path}")
        else:
            logger.warning(f"数据为空，未保存到 {save_path}")
