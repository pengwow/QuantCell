from backtesting import Strategy
from backtesting.lib import crossover
import pandas as pd


class SmaCross(Strategy):
    """
    基于SMA交叉的策略
    当短期移动平均线上穿长期移动平均线时买入
    当短期移动平均线下穿长期移动平均线时卖出
    """
    # 策略参数
    n1 = 10  # 短期移动平均线周期
    n2 = 20  # 长期移动平均线周期
    
    def init(self):
        """初始化策略"""
        # 计算短期和长期移动平均线
        self.sma1 = self.I(self.compute_sma, self.data.Close, self.n1)
        self.sma2 = self.I(self.compute_sma, self.data.Close, self.n2)
    
    def compute_sma(self, data, period):
        """
        计算简单移动平均线
        
        :param data: 价格数据
        :param period: 周期
        :return: 移动平均线
        """
        return pd.Series(data).rolling(period).mean()
    
    def next(self):
        """每根K线执行一次"""
        # 当短期均线上穿长期均线时买入
        if crossover(self.sma1, self.sma2):
            self.buy()
        # 当短期均线下穿长期均线时卖出
        elif crossover(self.sma2, self.sma1):
            self.sell()