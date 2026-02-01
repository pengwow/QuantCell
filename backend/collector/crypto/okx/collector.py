# OKX数据收集器
import sys
from pathlib import Path
import pandas as pd
import requests
from loguru import logger

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))

from collector.base import BaseCollector
from collector.base.utils import deco_retry
from exchange.crypto.base import CryptoBaseCollector
from exchange.okx.downloader import OKXDownloader


class OKXCollector(CryptoBaseCollector):
    """
    OKX数据收集器，用于从OKX交易所收集加密货币K线数据
    """
    
    def __init__(
        self,
        save_dir,
        start=None,
        end=None,
        interval="1d",
        max_workers=1,
        max_collector_count=2,
        delay=0,
        check_data_length=None,
        limit_nums=None,
        candle_type='spot',
        symbols=None,
        mode='inc',  # 添加模式参数，支持inc（增量）和full（全量），默认inc
    ):
        """
        初始化OKX数据收集器
        
        :param save_dir: 数据保存目录
        :param start: 开始时间
        :param end: 结束时间
        :param interval: 时间间隔，如'1m', '1h', '1d'等
        :param max_workers: 最大工作线程数
        :param max_collector_count: 最大收集次数
        :param delay: 请求延迟时间（秒）
        :param check_data_length: 数据长度检查阈值
        :param limit_nums: 限制收集的标的数量，用于调试
        :param candle_type: 蜡烛图类型，可选'spot'（现货）、'futures'（期货）或'option'（期权）
        :param symbols: 交易对列表，如['BTC-USDT', 'ETH-USDT']，如果为None则获取全量交易对
        :param mode: 下载模式，可选'inc'（增量）或'full'（全量），默认'inc'
        """
        # 先设置必要的属性，再调用父类的__init__方法
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
            mode=mode,  # 传递模式参数
        )
        
        self.downloader = OKXDownloader(candle_type=candle_type)
    
    @property
    def _timezone(self):
        """获取时区"""
        return "UTC"
    
    @deco_retry(max_retry=3, delay=1.0)
    def get_all_symbols(self):
        """
        从OKX API获取全量交易对列表
        
        :return: 交易对列表
        """
        try:
            if self.candle_type == 'spot':
                # 现货交易对
                url = 'https://www.okx.com/api/v5/public/instruments'
                params = {'instType': 'SPOT'}
            elif self.candle_type == 'futures':
                # 合约交易对
                url = 'https://www.okx.com/api/v5/public/instruments'
                params = {'instType': 'SWAP'}
            else:
                # 其他类型暂不支持
                logger.warning(f"暂不支持获取{self.candle_type}类型的交易对列表")
                return []
            
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            # 提取交易对列表
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
        # 如果有指定的交易对列表，直接返回
        if hasattr(self, 'symbols') and self.symbols:
            return self.symbols
        
        # 否则从API获取全量交易对列表
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
            # 将时间转换为字符串格式
            start_date = start_datetime.strftime('%Y-%m-%d')
            end_date = end_datetime.strftime('%Y-%m-%d')
            
            logger.info(f"开始下载 {symbol} {interval} 数据，时间范围: {start_date} 至 {end_date}")
            
            # 使用下载器下载数据
            df = self.downloader.download(symbol, interval, start_date, end_date)
            
            if df.empty:
                logger.warning(f"{symbol} {interval} 数据为空")
                return df
            
            # 数据处理
            df['timestamp'] = df['open_time']
            df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
            df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
            
            # 过滤时间范围
            # 将开始和结束时间转换为毫秒时间戳进行比较
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
        df = self.downloader.download(symbol, timeframe, start_date, end_date)
        if not df.empty:
            save_path = self.save_dir / f"{symbol}.csv"
            self.downloader.save_data(df, save_path)
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
            from collector.scripts.convert_to_qlib import \
                convert_crypto_to_qlib
            
            logger.info(f"开始将CSV数据转换为QLib格式...")
            logger.info(f"CSV目录: {csv_dir}")
            logger.info(f"QLib目录: {qlib_dir}")
            
            # 设置时间间隔
            if interval is None:
                interval = self.interval
            
            # 转换频率格式，QLib使用'day'而不是'1d'
            qlib_freq = "day" if interval == "1d" else interval
            
            # 调用转换脚本
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
        # 执行数据收集
        result = super().collect_data(progress_callback=progress_callback)
        return result
