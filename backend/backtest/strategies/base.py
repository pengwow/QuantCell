# 基础策略类
# 扩展Backtesting.py的Strategy类，添加获取不同时间周期数据的功能

from backtesting import Strategy
from backtesting.lib import crossover
import pandas as pd
from loguru import logger


class BaseStrategy(Strategy):
    """
    基础策略类，扩展Backtesting.py的Strategy类
    添加获取不同时间周期数据的功能
    """
    
    def __init__(self, broker, data, params):
        """
        初始化策略
        
        Args:
            broker: 经纪人实例
            data: 主周期数据
            params: 策略参数
        """
        super().__init__(broker, data, params)
        self.symbol = None
        self.data_manager = None
        
        # 从数据中提取交易对符号
        if hasattr(data, 'symbol'):
            self.symbol = data.symbol
        elif hasattr(data, 'name'):
            self.symbol = data.name
        
        logger.info(f"基础策略初始化成功，交易对: {self.symbol}")
    
    def set_data_manager(self, data_manager):
        """
        设置数据管理器实例
        
        Args:
            data_manager: 数据管理器实例
        """
        self.data_manager = data_manager
        logger.info(f"数据管理器已设置到策略实例，交易对: {self.symbol}")
    
    def get_data(self, interval):
        """
        获取指定时间周期的数据
        
        Args:
            interval: 时间周期，例如 '1m', '5m', '15m', '30m', '1h', '4h', '1d', '1w'
            
        Returns:
            pd.DataFrame: 指定周期的K线数据，与主周期数据格式一致
        """
        if not self.data_manager:
            logger.error(f"数据管理器未初始化，交易对: {self.symbol}")
            return pd.DataFrame()
        
        if not self.symbol:
            logger.error("交易对符号未设置")
            return pd.DataFrame()
        
        try:
            # 从数据管理器获取指定周期的数据
            data = self.data_manager.get_data(self.symbol, interval)
            logger.debug(f"成功获取 {self.symbol} 的 {interval} 周期数据，共 {len(data)} 条")
            return data
        except Exception as e:
            logger.error(f"获取 {self.symbol} 的 {interval} 周期数据失败: {e}")
            logger.exception(e)
            return pd.DataFrame()
    
    def get_supported_intervals(self):
        """
        获取支持的时间周期列表
        
        Returns:
            List[str]: 支持的时间周期列表
        """
        if self.data_manager:
            return self.data_manager.get_supported_intervals()
        return []
