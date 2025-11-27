# 加密货币基础类
import abc
from pathlib import Path

import pandas as pd
from loguru import logger

from ..base import BaseCollector


class CryptoBaseCollector(BaseCollector):
    """加密货币基础收集器类，定义加密货币数据收集的通用接口和功能"""
    
    def __init__(
        self,
        save_dir: [str, Path],
        start=None,
        end=None,
        interval="1d",
        max_workers=1,
        max_collector_count=2,
        delay=0,
        check_data_length: int = None,
        limit_nums: int = None,
    ):
        """
        初始化加密货币收集器
        
        :param save_dir: 数据保存目录
        :param start: 开始时间
        :param end: 结束时间
        :param interval: 时间间隔，如'1m', '1h', '1d'等
        :param max_workers: 最大工作线程数
        :param max_collector_count: 最大收集次数
        :param delay: 请求延迟时间（秒）
        :param check_data_length: 数据长度检查阈值
        :param limit_nums: 限制收集的标的数量，用于调试
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
        )
        
        # 初始化加密货币相关配置
        self.candle_names = [
            'open_time', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_volume', 'count', 'taker_buy_volume',
            'taker_buy_quote_volume', 'ignore'
        ]
    
    @property
    @abc.abstractmethod
    def _timezone(self):
        """获取时区"""
        raise NotImplementedError("请重写_timezone属性")
    
    @staticmethod
    def format_candle(candle: list) -> dict:
        """
        格式化K线数据
        
        :param candle: K线数据列表
        :return: 格式化后的K线数据字典
        """
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
            ignore=candle[11]
        )
    
    def normalize_symbol(self, symbol):
        """
        标准化加密货币符号，去除'/'分隔符
        
        :param symbol: 加密货币符号，如'BTC/USDT'
        :return: 标准化后的符号，如'BTCUSDT'
        """
        return symbol.replace('/', '')
    
    def get_instrument_list(self):
        """
        获取加密货币标的列表
        
        :return: 加密货币标的列表
        """
        # 默认返回空列表，子类需要重写此方法
        logger.warning("get_instrument_list方法未被重写，返回空列表")
        return []
