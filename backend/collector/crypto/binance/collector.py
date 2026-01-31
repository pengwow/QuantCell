# 币安数据收集器
import sys
from pathlib import Path
import pandas as pd
import requests
from loguru import logger

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))

from backend.collector.base import BaseCollector
from backend.collector.base.utils import deco_retry
from backend.exchange.crypto.base import CryptoBaseCollector
from backend.exchange.binance.downloader import BinanceDownloader


class BinanceCollector(CryptoBaseCollector):
    """币安数据收集器，用于从币安交易所收集加密货币K线数据"""
    
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
        初始化币安数据收集器
        
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
        :param symbols: 交易对列表，如['BTCUSDT', 'ETHUSDT']，如果为None则获取全量交易对
        :param mode: 下载模式，可选'inc'（增量）或'full'（全量），默认'inc'
        """
        # 先设置必要的属性，再调用父类的__init__方法
        self.candle_type = candle_type
        self.symbols = symbols
        self.downloader = BinanceDownloader(self.candle_type)
        
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
        
        self.candle_names = [
            'open_time', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_volume', 'count', 'taker_buy_volume',
            'taker_buy_quote_volume', 'ignore'
        ]
    
    @property
    def _timezone(self):
        """获取时区"""
        return "UTC"
    
    @deco_retry(max_retry=3, delay=1.0)
    def get_all_symbols(self):
        """
        从Binance API获取全量交易对列表
        
        :return: 交易对列表
        """
        try:
            if self.candle_type == 'spot':
                # 现货交易对
                url = 'https://api.binance.com/api/v3/exchangeInfo'
            elif self.candle_type == 'futures':
                # 合约交易对
                url = 'https://fapi.binance.com/fapi/v1/exchangeInfo'
            else:
                # 其他类型暂不支持
                logger.warning(f"暂不支持获取{self.candle_type}类型的交易对列表")
                return []
            
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            
            # 提取交易对列表
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
        # 如果有指定的交易对列表，直接返回
        if hasattr(self, 'symbols'):
            # 如果symbols为空列表或None，直接返回，不获取全量交易对
            if self.symbols is None:
                # 如果symbols为None，获取全量交易对列表
                return self.get_all_symbols()
            elif isinstance(self.symbols, (list, tuple)) and len(self.symbols) == 0:
                # 如果symbols为空列表，返回空列表
                return []
            else:
                # 否则返回指定的交易对列表
                return self.symbols
        
        # 否则从API获取全量交易对列表
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
            # 将时间转换为字符串格式
            start_date = start_datetime.strftime('%Y-%m-%d')
            end_date = end_datetime.strftime('%Y-%m-%d')
            
            logger.info(f"开始下载 {symbol} {interval} 数据，时间范围: {start_date} 至 {end_date}")
            
            # 使用下载器下载数据
            df = self.downloader.download(symbol, interval, start_date, end_date, progress_callback)
            
            if df.empty:
                logger.warning(f"{symbol} {interval} 数据为空")
                return pd.DataFrame()  # 如果下载的数据为空，返回空DataFrame
            
            # 数据处理
            logger.info(f"原始数据行数: {len(df)}")
            logger.info(f"原始数据类型: {df.dtypes}")
            
            # 1. 确保open_time列是数值类型
            logger.info("开始处理open_time列...")
            
            # 转换open_time列为数值类型，无法转换的值设为NaN
            df['open_time'] = pd.to_numeric(df['open_time'], errors='coerce')
            
            # 过滤掉open_time为NaN的行
            df = df.dropna(subset=['open_time'])
            logger.info(f"转换为数值类型后的数据行数: {len(df)}")
            
            if df.empty:
                logger.warning(f"{symbol} {interval} 数据在转换为数值类型后为空")
                return pd.DataFrame()  # 如果转换后的数据为空，返回空DataFrame
            
            # 2. 记录open_time列的统计信息
            logger.info(f"open_time列的统计信息:")
            logger.info(f"  最小值: {df['open_time'].min()}")
            logger.info(f"  最大值: {df['open_time'].max()}")
            logger.info(f"  平均值: {df['open_time'].mean()}")
            
            # 3. 转换为datetime，处理无效时间戳
            logger.info("开始转换时间戳...")
            
            # 自动检测时间戳单位
            # 13位数字: 毫秒级 (ms)
            # 16位数字: 微秒级 (us)
            # 19位数字: 纳秒级 (ns)
            first_open_time = df['open_time'].iloc[0]
            timestamp_length = len(str(int(first_open_time)))
            
            logger.info(f"第一个时间戳: {first_open_time}，长度: {timestamp_length}")
            
            # 根据时间戳长度直接计算正确的单位和转换值
            df['timestamp'] = pd.Series(dtype='datetime64[ns]')
            valid_count = 0
            
            # 方法1：根据长度直接转换
            try:
                if timestamp_length == 13:  # 毫秒
                    df['timestamp'] = pd.to_datetime(df['open_time'], unit='ms', errors='coerce')
                elif timestamp_length == 16:  # 微秒
                    # 先将微秒转换为秒，再转换为datetime
                    df['timestamp'] = pd.to_datetime(df['open_time'] / 1000000, unit='s', errors='coerce')
                elif timestamp_length == 19:  # 纳秒
                    df['timestamp'] = pd.to_datetime(df['open_time'], unit='ns', errors='coerce')
                else:  # 其他长度，尝试多种单位
                    logger.warning(f"时间戳长度 {timestamp_length} 不常见，尝试多种转换方法...")
                    
                    # 尝试直接转换（适用于已格式化的字符串）
                    df['timestamp'] = pd.to_datetime(df['open_time'], errors='coerce')
                    valid_count = df['timestamp'].notna().sum()
                    
                    if valid_count == 0:
                        # 尝试除以不同的系数转换为秒
                        for divisor in [1000, 1000000, 1000000000]:
                            df['timestamp'] = pd.to_datetime(df['open_time'] / divisor, unit='s', errors='coerce')
                            valid_count = df['timestamp'].notna().sum()
                            if valid_count > 0:
                                logger.info(f"通过除以 {divisor} 转换成功，有效日期数量: {valid_count}")
                                break
                
                valid_count = df['timestamp'].notna().sum()
                logger.info(f"时间戳转换结果: 有效日期 {valid_count} 个，无效日期 {len(df) - valid_count} 个")
            except Exception as e:
                logger.error(f"时间戳转换异常: {e}")
                df['timestamp'] = pd.to_datetime(df['open_time'], errors='coerce')
                valid_count = df['timestamp'].notna().sum()
            
            # 记录转换结果
            valid_dates = df['timestamp'].notna().sum()
            invalid_dates = df['timestamp'].isna().sum()
            logger.info(f"时间戳转换结果: 有效日期 {valid_dates} 个，无效日期 {invalid_dates} 个")
            
            # 4. 记录无效时间戳的具体值
            if invalid_dates > 0:
                invalid_times = df[df['timestamp'].isna()]['open_time'].tolist()
                logger.warning(f"无效时间戳值: {invalid_times}")
            
            # 5. 过滤掉无效时间戳的行
            filtered_df = df.dropna(subset=['open_time'])
            
            # 6. 记录过滤掉的无效行数量
            if len(filtered_df) < len(df):
                logger.warning(f"过滤掉了 {len(df) - len(filtered_df)} 行无效时间戳数据")
            
            # 7. 只保留需要的列，使用原始open_time作为timestamp
            # 使用loc[:, []]语法确保返回DataFrame类型
            filtered_df = filtered_df.loc[:, ['open_time', 'open', 'high', 'low', 'close', 'volume']]
            filtered_df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
            
            # 8. 检测时间戳单位并调整
            if not filtered_df.empty:
                first_timestamp = filtered_df['timestamp'].iloc[0]
                timestamp_length = len(str(int(first_timestamp)))
                logger.info(f"检测到时间戳长度: {timestamp_length}")
                
                # 调整时间戳单位为毫秒
                if timestamp_length == 16:  # 微秒
                    filtered_df['timestamp'] = filtered_df['timestamp'] // 1000
                    logger.info("时间戳已从微秒调整为毫秒")
                elif timestamp_length == 19:  # 纳秒
                    filtered_df['timestamp'] = filtered_df['timestamp'] // 1000000
                    logger.info("时间戳已从纳秒调整为毫秒")
                elif timestamp_length == 10:  # 秒
                    filtered_df['timestamp'] = filtered_df['timestamp'] * 1000
                    logger.info("时间戳已从秒调整为毫秒")
            
            # 9. 过滤时间范围
            # 将开始和结束时间转换为毫秒时间戳进行比较
            start_timestamp = int(start_datetime.timestamp() * 1000)
            end_timestamp = int(end_datetime.timestamp() * 1000)
            logger.info(f"时间范围过滤: {start_timestamp} 至 {end_timestamp}")
            logger.info(f"过滤前数据量: {len(filtered_df)}")
            
            filtered_df = filtered_df[(filtered_df['timestamp'] >= start_timestamp) & (filtered_df['timestamp'] <= end_timestamp)]
            logger.info(f"过滤后数据量: {len(filtered_df)}")

            logger.info(f"成功下载 {symbol} {interval} 数据，共 {len(filtered_df)} 条")
            
            # 确保返回的DataFrame至少包含必要的列
            if not filtered_df.empty:
                required_columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
                if all(col in filtered_df.columns for col in required_columns):
                    logger.info(f"数据包含所有必要列: {required_columns}")
                else:
                    missing_cols = [col for col in required_columns if col not in filtered_df.columns]
                    logger.warning(f"数据缺少必要列: {missing_cols}")
                    # 尝试重新下载
                    logger.info("尝试重新下载数据...")
                    df = self.downloader.download(symbol, interval, start_date, end_date, progress_callback)
                    if not df.empty:
                        filtered_df = df.loc[:, ['open_time', 'open', 'high', 'low', 'close', 'volume']]
                        filtered_df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
                        logger.info(f"重新下载后的数据量: {len(filtered_df)}")
            
            return filtered_df
        except Exception as e:
            logger.error(f"下载 {symbol} {interval} 数据失败: {e}")
            logger.exception(e)  # 记录完整的异常堆栈
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
            from backend.collector.scripts.convert_to_qlib import \
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
