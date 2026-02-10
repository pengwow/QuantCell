# 基础策略类
# 使用自研策略框架实现

import pandas as pd
from loguru import logger
from strategy.core import StrategyCore

# 全局数据管理器实例
_data_manager = None


def set_data_manager(data_manager):
    """
    设置全局数据管理器实例

    Args:
        data_manager: 数据管理器实例
    """
    global _data_manager
    _data_manager = data_manager
    logger.info("全局数据管理器已设置")


class BaseStrategy(StrategyCore):
    """
    基础策略类，使用自研 StrategyCore 框架
    添加获取不同时间周期数据的功能
    """

    def __init__(self, params: dict = None):
        """
        初始化策略

        Args:
            params: 策略参数
        """
        super().__init__(params or {})
        self.symbol = None

    def set_symbol(self, symbol: str):
        """
        设置交易对符号

        Args:
            symbol: 交易对符号
        """
        self.symbol = symbol
        logger.info(f"策略交易对设置为: {symbol}")

    def get_data(self, interval: str) -> pd.DataFrame:
        """
        获取指定时间周期的数据

        Args:
            interval: 时间周期，例如 '1m', '5m', '15m', '30m', '1h', '4h', '1d', '1w'

        Returns:
            pd.DataFrame: 指定周期的K线数据
        """
        global _data_manager

        if not _data_manager:
            logger.error("数据管理器未初始化")
            return pd.DataFrame()

        if not self.symbol:
            logger.error("交易对符号未设置")
            return pd.DataFrame()

        try:
            # 从数据管理器获取指定周期的数据
            data = _data_manager.get_data(self.symbol, interval)
            logger.debug(f"成功获取 {self.symbol} 的 {interval} 周期数据，共 {len(data)} 条")
            return data
        except Exception as e:
            logger.error(f"获取 {self.symbol} 的 {interval} 周期数据失败: {e}")
            logger.exception(e)
            return pd.DataFrame()

    def get_supported_intervals(self) -> list:
        """
        获取支持的时间周期列表

        Returns:
            list: 支持的时间周期列表
        """
        global _data_manager

        if _data_manager:
            return _data_manager.get_supported_intervals()
        return []

    def calculate_indicators(self, data: pd.DataFrame) -> dict:
        """
        计算策略所需的指标（子类必须实现）

        Args:
            data: K线数据

        Returns:
            dict: 计算得到的指标字典
        """
        # 默认实现，返回空字典
        return {}

    def generate_signals(self, indicators: dict) -> dict:
        """
        根据指标生成交易信号（子类必须实现）

        Args:
            indicators: 计算得到的指标字典

        Returns:
            dict: 交易信号字典
        """
        # 默认实现，返回空信号
        return {
            'entries': pd.Series(False, index=indicators.get('sma1', pd.Series()).index if indicators else []),
            'exits': pd.Series(False, index=indicators.get('sma1', pd.Series()).index if indicators else [])
        }
