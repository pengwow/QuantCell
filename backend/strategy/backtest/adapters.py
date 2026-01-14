# 回测引擎适配器
# 用于将策略核心与不同的回测引擎连接
# 支持 backtesting.py 和 vectorbt

import pandas as pd
from abc import ABC, abstractmethod
from typing import Any
from ..core import StrategyCore


class StrategyAdapter(ABC):
    """
    策略适配器抽象类，定义回测引擎的适配接口
    """
    
    def __init__(self, strategy_core: StrategyCore):
        """
        初始化适配器
        
        Args:
            strategy_core: 策略核心实例
        """
        self.strategy_core = strategy_core
    
    @abstractmethod
    def run_backtest(self, data: pd.DataFrame, **kwargs) -> Any:
        """
        运行回测
        
        Args:
            data: K线数据
            **kwargs: 额外的回测参数
        
        Returns:
            Any: 回测结果
        """
        pass


class BacktestingPyAdapter(StrategyAdapter):
    """
    backtesting.py 适配器
    """
    
    def run_backtest(self, data: pd.DataFrame, **kwargs) -> Any:
        """
        运行 backtesting.py 回测
        
        Args:
            data: K线数据
            **kwargs: 额外的回测参数，如cash, commission等
        
        Returns:
            Any: 回测结果
        """
        from backtesting import Backtest, Strategy
        
        # 保存策略核心引用
        strategy_core = self.strategy_core
        
        # 创建策略类
        class BacktestingPyStrategy(Strategy):
            # 设置策略参数
            params = {}
            for key, value in strategy_core.params.items():
                params[key] = value
            
            def init(self):
                # 计算指标
                result = strategy_core.run(self.data.df)
                self.indicators = result['indicators']
                self.signals = result['signals']
                
                # 注册指标以便绘图
                for name, indicator in self.indicators.items():
                    if isinstance(indicator, pd.Series):
                        setattr(self, name, self.I(lambda x: x, indicator))
            
            def next(self):
                # 获取当前索引
                current_idx = len(self.data) - 1
                
                # 检查是否支持多头和空头信号
                has_long_short = 'long_entries' in self.signals and 'short_entries' in self.signals
                
                if has_long_short:
                    # 多头交易
                    if self.signals['long_entries'].iloc[current_idx]:
                        # 确保当前没有空头仓位
                        if self.position < 0:
                            self.position = 0
                        # 获取多头仓位大小
                        long_size = self.signals.get('long_sizes', pd.Series([1.0])).iloc[current_idx]
                        self.buy(size=long_size)
                    elif (self.signals['long_exits'].iloc[current_idx] or 
                         self.signals.get('take_profit', pd.Series([False])).iloc[current_idx] or 
                         self.signals.get('stop_loss', pd.Series([False])).iloc[current_idx]):
                        # 平多头仓位
                        if self.position > 0:
                            self.position = 0
                    
                    # 空头交易
                    if self.signals['short_entries'].iloc[current_idx]:
                        # 确保当前没有多头仓位
                        if self.position > 0:
                            self.position = 0
                        # 获取空头仓位大小
                        short_size = self.signals.get('short_sizes', pd.Series([1.0])).iloc[current_idx]
                        self.sell(size=short_size)
                    elif (self.signals['short_exits'].iloc[current_idx] or 
                         self.signals.get('take_profit', pd.Series([False])).iloc[current_idx] or 
                         self.signals.get('stop_loss', pd.Series([False])).iloc[current_idx]):
                        # 平空头仓位
                        if self.position < 0:
                            self.position = 0
                else:
                    # 兼容旧接口
                    # 执行交易 - 入场信号
                    if self.signals.get('entries', pd.Series([False])).iloc[current_idx]:
                        # 获取仓位大小
                        position_size = self.signals.get('position_sizes', pd.Series([1.0])).iloc[current_idx]
                        self.buy(size=position_size)
                    # 执行交易 - 出场信号（包括止盈）
                    elif (self.signals.get('exits', pd.Series([False])).iloc[current_idx] or 
                         self.signals.get('take_profit', pd.Series([False])).iloc[current_idx]):
                        self.sell()
                    # 执行交易 - 止损信号
                    elif self.signals.get('stop_loss', pd.Series([False])).iloc[current_idx]:
                        self.sell()
        
        # 运行回测
        bt = Backtest(data, BacktestingPyStrategy, **kwargs)
        results = bt.run()
        return results


class VectorBTAdapter(StrategyAdapter):
    """
    vectorbt 适配器
    """
    
    def run_backtest(self, data: pd.DataFrame, **kwargs) -> Any:
        """
        运行 vectorbt 回测
        
        Args:
            data: K线数据
            **kwargs: 额外的回测参数，如init_cash, fees等
        
        Returns:
            Any: 回测结果
        """
        import vectorbt as vbt
        
        # 运行策略获取信号
        result = self.strategy_core.run(data)
        signals = result['signals']
        
        # 提取价格数据
        price = data['Close']
        
        # 检查是否支持多头和空头信号
        has_long_short = 'long_entries' in signals and 'short_entries' in signals
        
        if has_long_short:
            # 合并多头出场信号（包括止盈止损）
            long_exits = signals['long_exits']
            if 'take_profit' in signals:
                long_exits = long_exits | signals['take_profit']
            if 'stop_loss' in signals:
                long_exits = long_exits | signals['stop_loss']
            
            # 合并空头出场信号（包括止盈止损）
            short_exits = signals['short_exits']
            if 'take_profit' in signals:
                short_exits = short_exits | signals['take_profit']
            if 'stop_loss' in signals:
                short_exits = short_exits | signals['stop_loss']
            
            # 获取仓位大小
            size = signals.get('long_sizes', pd.Series([1.0]))
            
            # 运行 vectorbt 回测 - 支持多头和空头，兼容旧版本不支持 short_size
            try:
                # 尝试使用 short_size 参数（新版本 vectorbt）
                pf = vbt.Portfolio.from_signals(
                    price,
                    entries=signals['long_entries'],
                    exits=long_exits,
                    short_entries=signals['short_entries'],
                    short_exits=short_exits,
                    size=size,
                    short_size=signals.get('short_sizes', pd.Series([1.0])),
                    **kwargs
                )
            except TypeError:
                # 回退到不使用 short_size 参数（旧版本 vectorbt）
                pf = vbt.Portfolio.from_signals(
                    price,
                    entries=signals['long_entries'],
                    exits=long_exits,
                    short_entries=signals['short_entries'],
                    short_exits=short_exits,
                    size=size,
                    **kwargs
                )
        else:
            # 兼容旧接口
            # 合并出场信号（包括止盈止损）
            exits = signals.get('exits', pd.Series([False]))
            if 'take_profit' in signals:
                exits = exits | signals['take_profit']
            if 'stop_loss' in signals:
                exits = exits | signals['stop_loss']
            
            # 获取仓位大小
            size = signals.get('position_sizes', pd.Series([1.0]))
            
            # 运行 vectorbt 回测
            pf = vbt.Portfolio.from_signals(
                price,
                entries=signals.get('entries', pd.Series([False])),
                exits=exits,
                size=size,
                **kwargs
            )
        
        return pf
