# 基于SMA交叉的策略
# 使用自研策略框架实现

import pandas as pd
from strategy.core import StrategyCore


class SmaCross(StrategyCore):
    """
    基于SMA交叉的策略
    当短期移动平均线上穿长期移动平均线时买入
    当短期移动平均线下穿长期移动平均线时卖出
    """

    def __init__(self, params: dict = None):
        """
        初始化策略

        Args:
            params: 策略参数，包含 n1（短期周期）和 n2（长期周期）
        """
        default_params = {
            'n1': 10,  # 短期移动平均线周期
            'n2': 20,  # 长期移动平均线周期
        }
        if params:
            default_params.update(params)
        super().__init__(default_params)

    def calculate_indicators(self, data: pd.DataFrame) -> dict:
        """
        计算策略所需的指标

        Args:
            data: K线数据

        Returns:
            dict: 包含SMA指标的字典
        """
        n1 = self.params.get('n1', 10)
        n2 = self.params.get('n2', 20)

        # 计算移动平均线
        sma1 = data['Close'].rolling(window=n1).mean()
        sma2 = data['Close'].rolling(window=n2).mean()

        return {
            'sma1': sma1,
            'sma2': sma2
        }

    def generate_signals(self, indicators: dict) -> dict:
        """
        根据指标生成交易信号

        Args:
            indicators: 计算得到的指标字典

        Returns:
            dict: 交易信号字典
        """
        sma1 = indicators['sma1']
        sma2 = indicators['sma2']

        # 计算交叉信号
        # 短期均线上穿长期均线（金叉）
        long_entries = (sma1 > sma2) & (sma1.shift(1) <= sma2.shift(1))
        # 短期均线下穿长期均线（死叉）
        long_exits = (sma1 < sma2) & (sma1.shift(1) >= sma2.shift(1))

        return {
            'entries': long_entries,
            'exits': long_exits
        }

    def generate_long_signals(self, indicators: dict) -> tuple:
        """
        生成多头信号

        Args:
            indicators: 指标字典

        Returns:
            tuple: (多头入场信号, 多头出场信号)
        """
        sma1 = indicators['sma1']
        sma2 = indicators['sma2']

        # 金叉买入
        long_entries = (sma1 > sma2) & (sma1.shift(1) <= sma2.shift(1))
        # 死叉卖出
        long_exits = (sma1 < sma2) & (sma1.shift(1) >= sma2.shift(1))

        return long_entries, long_exits
