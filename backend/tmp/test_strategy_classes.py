#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
直接测试策略类和配置类
"""

import sys
from pathlib import Path

# 添加项目路径
backend_path = Path(__file__).resolve().parent
sys.path.insert(0, str(backend_path))

from utils.logger import get_logger, LogType
logger = get_logger(__name__, LogType.APPLICATION)

def test_strategy_classes():
    try:
        from strategy.core import Strategy, StrategyConfig, InstrumentId
        from decimal import Decimal
        
        # 添加项目路径
        backend_path = Path(__file__).resolve().parent
        if str(backend_path) not in sys.path:
            sys.path.insert(0, str(backend_path))
        
        # 添加策略目录到路径
        strategies_dir = backend_path / 'strategies'
        if str(strategies_dir) not in sys.path:
            sys.path.insert(0, str(strategies_dir))
        
        # 首先测试导入策略模块
        logger.info("正在导入策略模块...")
        import importlib
        strategy_module = importlib.import_module('sma_cross_simple')
        
        logger.info(f"策略模块内容: {dir(strategy_module)}")
        
        # 获取策略类和配置类
        SmaCrossSimple = getattr(strategy_module, 'SmaCrossSimple')
        SmaCrossSimpleConfig = getattr(strategy_module, 'SmaCrossSimpleConfig')
        
        logger.info(f"找到策略类: {SmaCrossSimple}")
        logger.info(f"找到配置类: {SmaCrossSimpleConfig}")
        
        # 创建测试配置
        logger.info("正在创建配置对象...")
        instrument_id = InstrumentId(symbol='BTCUSDT', venue='BINANCE')
        config = SmaCrossSimpleConfig(
            instrument_ids=[instrument_id],
            bar_types=['1-HOUR'],
            trade_size=Decimal('0.1'),
            fast_period=10,
            slow_period=30
        )
        
        logger.info(f"配置对象类型: {type(config)}")
        logger.info(f"配置对象: {config}")
        logger.info(f"配置对象的 instrument_ids: {config.instrument_ids}")
        logger.info(f"配置对象的属性: {dir(config)}")
        
        # 创建策略对象
        logger.info("正在创建策略对象...")
        strategy = SmaCrossSimple(config)
        
        logger.info(f"策略对象类型: {type(strategy)}")
        logger.info(f"策略对象: {strategy}")
        logger.info(f"策略对象的属性: {dir(strategy)}")
        
        # 检查策略对象的 config 属性
        if hasattr(strategy, 'config'):
            logger.info(f"策略对象的 config 属性类型: {type(strategy.config)}")
            logger.info(f"策略对象的 config 属性值: {strategy.config}")
        
        if hasattr(strategy, '_config'):
            logger.info(f"策略对象的 _config 属性类型: {type(strategy._config)}")
            logger.info(f"策略对象的 _config 属性值: {strategy._config}")
        
        logger.info("测试成功！")
        
    except Exception as e:
        logger.error(f"测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_strategy_classes()
