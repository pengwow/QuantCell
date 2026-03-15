#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模拟 API 调用测试
"""

import sys
from pathlib import Path

# 添加项目路径
backend_path = Path(__file__).resolve().parent
sys.path.insert(0, str(backend_path))

from utils.logger import get_logger, LogType
logger = get_logger(__name__, LogType.APPLICATION)

def test_api_simulation():
    try:
        logger.info("开始模拟 API 调用测试")
        
        # 模拟 API 收到的请求数据
        logger.info("模拟 API 收到的请求数据...")
        
        # 模拟 strategy_config 和 backtest_config
        strategy_config = {
            "strategy_name": "sma_cross_simple",
            "params": {
                "fast_period": 10,
                "slow_period": 30,
                "trade_size": 0.1
            }
        }
        
        backtest_config = {
            "symbols": ["BTCUSDT"],
            "interval": "1h",
            "start_time": "2024-01-01 00:00:00",
            "end_time": "2024-01-31 23:59:59",
            "initial_cash": 100000.0,
            "commission": 0.001,
            "engine_type": "event",
            "base_currency": "USDT",
            "leverage": 1.0,
            "venue": "SIM"
        }
        
        logger.info(f"strategy_config: {strategy_config}")
        logger.info(f"backtest_config: {backtest_config}")
        
        # 测试直接调用 _load_event_strategy_multi
        logger.info("测试直接调用 _load_event_strategy_multi...")
        
        from backtest.cli import _load_event_strategy_multi
        from nautilus_trader.test_kit.providers import TestInstrumentProvider
        from nautilus_trader.model.data import BarType
        
        # 创建测试数据
        instrument = TestInstrumentProvider.btcusdt_binance()
        instruments = {"BTCUSDT": instrument}
        
        bar_type_str = f"{instrument.id}-1-HOUR-LAST-EXTERNAL"
        bar_type = BarType.from_str(bar_type_str)
        bar_types = {"BTCUSDT": bar_type}
        
        strategy_name = strategy_config["strategy_name"]
        strategy_params = strategy_config["params"]
        
        logger.info(f"调用 _load_event_strategy_multi...")
        logger.info(f"strategy_name: {strategy_name}")
        logger.info(f"strategy_params: {strategy_params}")
        
        strategy = _load_event_strategy_multi(
            strategy_name, strategy_params, bar_types, instruments
        )
        
        if strategy:
            logger.info("策略加载成功！")
        else:
            logger.error("策略加载失败！")
            
    except Exception as e:
        logger.error(f"测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_api_simulation()
