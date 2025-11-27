# OKX数据下载器
import requests
import pandas as pd
from loguru import logger
from pathlib import Path


class OKXDownloader:
    """
    OKX数据下载器，用于从OKX交易所下载K线数据
    """
    
    def __init__(self, candle_type='spot'):
        """
        初始化OKX下载器
        
        :param candle_type: 蜡烛图类型，可选'spot'（现货）、'futures'（期货）或'option'（期权）
        """
        self.candle_type = candle_type
        
        # 设置API端点
        if candle_type == 'spot':
            self.base_url = 'https://www.okx.com/api/v5/market'
        elif candle_type == 'futures':
            self.base_url = 'https://www.okx.com/api/v5/market'
        else:
            self.base_url = 'https://www.okx.com/api/v5/market'
    
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
            # 转换时间格式
            start_ts = int(pd.Timestamp(start_date).timestamp() * 1000)
            end_ts = int(pd.Timestamp(end_date).timestamp() * 1000)
            
            # 设置请求参数
            params = {
                'instId': symbol,
                'bar': interval,
                'after': str(start_ts),
                'before': str(end_ts),
                'limit': '100'
            }
            
            # 发送请求
            response = requests.get(f'{self.base_url}/candles', params=params)
            response.raise_for_status()
            
            # 解析响应
            data = response.json()['data']
            
            if not data:
                return pd.DataFrame()
            
            # 转换为DataFrame
            df = pd.DataFrame(
                data, 
                columns=['open_time', 'open', 'high', 'low', 'close', 'volume', 'volume_currency', 'unknown']
            )
            
            # 转换数据类型
            df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
            df['open'] = pd.to_numeric(df['open'])
            df['high'] = pd.to_numeric(df['high'])
            df['low'] = pd.to_numeric(df['low'])
            df['close'] = pd.to_numeric(df['close'])
            df['volume'] = pd.to_numeric(df['volume'])
            
            # 按时间排序
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
            # 确保目录存在
            save_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 保存数据
            df.to_csv(save_path, index=False)
            logger.info(f"数据已保存到: {save_path}")
        except Exception as e:
            logger.error(f"保存数据失败: {e}")
