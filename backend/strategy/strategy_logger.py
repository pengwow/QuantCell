# -*- coding: utf-8 -*-
"""
策略专用日志模块

提供统一的策略日志接口，所有处理逻辑封装在内部。

使用方式：
    from strategy.strategy_logger import get_strategy_logger
    
    class MyStrategy(StrategyBase):
        def __init__(self, params):
            super().__init__(params)
            self.logger = get_strategy_logger("my_strategy")
            
        def on_bar(self, bar):
            self.logger.info("信号触发")
            self.logger.debug(f"价格: {bar['close']}")
"""

from utils.logger import get_strategy_logger, StrategyLogger

# 导出统一接口
__all__ = ['get_strategy_logger', 'StrategyLogger']
