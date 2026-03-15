#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试策略加载问题
"""

import sys
from pathlib import Path

# 添加项目路径
backend_path = Path(__file__).resolve().parent
sys.path.insert(0, str(backend_path))

from utils.logger import get_logger, LogType
logger = get_logger(__name__, LogType.APPLICATION)

# 测试策略加载
def test_strategy_loading():
    try:
        from backtest.cli import _load_event_strategy_multi
        from nautilus_trader.test_kit.providers import TestInstrumentProvider
        from nautilus_trader.model.data import BarType
        
        logger.info("开始测试策略加载")
        
        # 准备测试数据
        strategy_name = "sma_cross_simple"
        strategy_params = {
            "fast_period": 10,
            "slow_period": 30,
            "trade_size": 0.1
        }
        
        # 创建测试 instruments
        instrument = TestInstrumentProvider.btcusdt_binance()
        instruments = {"BTCUSDT": instrument}
        
        # 创建测试 bar_types
        bar_type_str = f"{instrument.id}-1-HOUR-LAST-EXTERNAL"
        bar_type = BarType.from_str(bar_type_str)
        bar_types = {"BTCUSDT": bar_type}
        
        logger.info(f"策略名称: {strategy_name}")
        logger.info(f"策略参数: {strategy_params}")
        logger.info(f"Instruments: {instruments}")
        logger.info(f"Bar types: {bar_types}")
        
        # 尝试加载策略
        logger.info("正在加载策略...")
        strategy = _load_event_strategy_multi(
            strategy_name, strategy_params, bar_types, instruments
        )
        
        if strategy:
            logger.info("策略加载成功！")
            logger.info(f"策略类型: {type(strategy)}")
            if hasattr(strategy, 'config'):
                logger.info(f"策略配置: {strategy.config}")
                logger.info(f"配置类型: {type(strategy.config)}")
                if hasattr(strategy.config, 'instrument_ids'):
                    logger.info(f"Instrument IDs: {strategy.config.instrument_ids}")
        else:
            logger.error("策略加载失败！")
            
    except Exception as e:
        logger.error(f"测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_strategy_loading()
