#!/usr/bin/env python3
"""
回测适配器模块

提供统一的回测适配器接口，支持多个回测框架
"""

from .base_adapter import BaseBacktestAdapter, BacktestResult, TradeRecord
from .quantcell_adapter import QuantCellAdapter
from .backtrader_adapter import BacktraderAdapter
from .freqtrade_adapter import FreqtradeAdapter

__all__ = [
    'BaseBacktestAdapter',
    'BacktestResult',
    'TradeRecord',
    'QuantCellAdapter',
    'BacktraderAdapter',
    'FreqtradeAdapter',
]
