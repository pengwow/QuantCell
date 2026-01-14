# SMA 交叉策略的策略核心实现
# 使用新的策略架构，与回测引擎无关
# 详细文档请查看: docs/sma_cross_strategy.md

import pandas as pd
from .core import StrategyCore


class SmaCrossCore(StrategyCore):
    """
    基于SMA交叉的策略核心
    
    详细文档请查看: docs/sma_cross_strategy.md
    """
    
    def __init__(self, params: dict):
        """
        初始化SMA交叉策略核心
        
        参数详情请查看: docs/sma_cross_strategy.md#51-smacrosscore-类
        """
        if not isinstance(params, dict):
            raise ValueError("参数必须是字典类型")
        
        # 设置默认参数
        default_params = {
            'n1': 10,
            'n2': 20,
            'initial_capital': 10000
        }
        # 合并用户参数和默认参数
        default_params.update(params)
        
        super().__init__(default_params)
        
    def calculate_indicators(self, data: pd.DataFrame):
        """
        计算SMA指标
        
        详细实现请查看: docs/sma_cross_strategy.md#511-calculate_indicatorsdata
        """
        if 'Close' not in data.columns:
            raise KeyError("数据中缺少Close列")
        
        # 获取策略参数
        n1 = self.params.get('n1', 10)
        n2 = self.params.get('n2', 20)
        
        # 计算短期和长期移动平均线
        close = data['Close']
        sma1 = close.rolling(window=n1).mean()
        sma2 = close.rolling(window=n2).mean()
        
        return {
            'sma1': sma1,
            'sma2': sma2
        }
    
    def generate_signals(self, indicators):
        """
        根据SMA指标生成交易信号
        
        详细实现请查看: docs/sma_cross_strategy.md#512-generate_signalsindicators
        """
        if 'sma1' not in indicators or 'sma2' not in indicators:
            raise KeyError("indicators中缺少sma1或sma2")
        
        sma1 = indicators['sma1']
        sma2 = indicators['sma2']
        
        # 生成交叉信号
        # 短期均线上穿长期均线 -> 买入信号
        entries = (sma1 > sma2) & (sma1.shift(1) <= sma2.shift(1))
        # 短期均线下穿长期均线 -> 卖出信号
        exits = (sma1 < sma2) & (sma1.shift(1) >= sma2.shift(1))
        
        # 支持多头和空头信号
        return {
            'entries': entries,
            'exits': exits,
            'long_entries': entries,
            'long_exits': exits,
            'short_entries': pd.Series(False, index=sma1.index),
            'short_exits': pd.Series(False, index=sma1.index)
        }
    
    def generate_stop_loss_take_profit(self, data, signals, indicators):
        """
        生成止损止盈信号
        
        详细实现请查看: docs/sma_cross_strategy.md#513-generate_stop_loss_take_profitdata-signals-indicators
        """
        # 默认实现，返回空信号
        return {
            'stop_loss': pd.Series(False, index=data.index),
            'take_profit': pd.Series(False, index=data.index)
        }
    
    def calculate_position_size(self, data, signals, indicators, capital):
        """
        计算仓位大小
        
        详细实现请查看: docs/sma_cross_strategy.md#514-calculate_position_sizedata-signals-indicators-capital
        """
        # 默认实现，返回固定仓位大小1.0
        return pd.Series(1.0, index=data.index)
