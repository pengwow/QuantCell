# 数据管理器
# 管理回测过程中的多周期数据

import pandas as pd
from pathlib import Path
from loguru import logger
from datetime import datetime

class DataManager:
    """
    数据管理器，用于管理不同时间周期的数据
    支持策略在回测过程中获取不同周期的数据
    """
    
    def __init__(self, data_service):
        """
        初始化数据管理器
        
        Args:
            data_service: 数据服务实例，用于获取K线数据
        """
        self.data_service = data_service
        self.data_cache = {}  # 数据缓存，格式：{symbol: {interval: data}}
        self.supported_intervals = ['1m', '5m', '15m', '30m', '1h', '4h', '1d', '1w']
        
        logger.info("数据管理器初始化成功")
    
    def preload_data(self, symbol, base_interval, start_time, end_time, preload_intervals=None):
        """
        预加载多种时间周期的数据
        
        Args:
            symbol: 交易对符号
            base_interval: 主回测周期
            start_time: 开始时间
            end_time: 结束时间
            preload_intervals: 需要预加载的周期列表，默认为None，加载所有支持的周期
        """
        if preload_intervals is None:
            preload_intervals = self.supported_intervals
        
        # 确保主周期在预加载列表中
        if base_interval not in preload_intervals:
            preload_intervals.append(base_interval)
        
        logger.info(f"开始预加载数据，交易对: {symbol}, 主周期: {base_interval}, 预加载周期: {preload_intervals}")
        
        # 初始化交易对的数据缓存
        if symbol not in self.data_cache:
            self.data_cache[symbol] = {}
        
        # 预加载数据
        for interval in preload_intervals:
            try:
                logger.info(f"预加载 {symbol} 的 {interval} 周期数据")
                
                # 调用数据服务获取K线数据
                kline_data = self.data_service.get_kline_data(
                    symbol=symbol,
                    interval=interval,
                    start_time=start_time,
                    end_time=end_time
                )
                
                # 将数据转换为DataFrame
                if kline_data and 'data' in kline_data:
                    df = pd.DataFrame(kline_data['data'])
                    # 确保时间列是datetime类型
                    if 'datetime' in df.columns:
                        df['datetime'] = pd.to_datetime(df['datetime'])
                        df.set_index('datetime', inplace=True)
                    elif 'open_time' in df.columns:
                        df['open_time'] = pd.to_datetime(df['open_time'])
                        df.set_index('open_time', inplace=True)
                    
                    # 缓存数据
                    self.data_cache[symbol][interval] = df
                    logger.info(f"成功预加载 {symbol} 的 {interval} 周期数据，共 {len(df)} 条")
                else:
                    logger.warning(f"未获取到 {symbol} 的 {interval} 周期数据")
            except Exception as e:
                logger.error(f"预加载 {symbol} 的 {interval} 周期数据失败: {e}")
                logger.exception(e)
    
    def get_data(self, symbol, interval):
        """
        获取指定交易对和周期的数据
        
        Args:
            symbol: 交易对符号
            interval: 时间周期
            
        Returns:
            pd.DataFrame: K线数据DataFrame
        """
        try:
            # 检查数据缓存
            if symbol in self.data_cache and interval in self.data_cache[symbol]:
                return self.data_cache[symbol][interval]
            
            logger.warning(f"未找到 {symbol} 的 {interval} 周期缓存数据，尝试动态加载")
            
            # 动态加载数据（如果没有预加载）
            # 这里简化处理，实际应该有更复杂的逻辑来确定时间范围
            return pd.DataFrame()
        except Exception as e:
            logger.error(f"获取 {symbol} 的 {interval} 周期数据失败: {e}")
            logger.exception(e)
            return pd.DataFrame()
    
    def get_supported_intervals(self):
        """
        获取支持的时间周期列表
        
        Returns:
            List[str]: 支持的时间周期列表
        """
        return self.supported_intervals
    
    def clear_cache(self, symbol=None):
        """
        清除数据缓存
        
        Args:
            symbol: 交易对符号，默认为None，清除所有交易对的缓存
        """
        if symbol is None:
            self.data_cache.clear()
            logger.info("已清除所有数据缓存")
        elif symbol in self.data_cache:
            del self.data_cache[symbol]
            logger.info(f"已清除 {symbol} 的数据缓存")
