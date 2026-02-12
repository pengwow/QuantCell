#!/usr/bin/env python3
"""
QuantCell 性能测试框架

用于对比 QuantCell、Freqtrade 和 Backtrader 三个框架的性能表现
"""

from .base_test import BasePerformanceTest, PerformanceMetrics
from .quantcell_test import QuantCellPerformanceTest
from .backtrader_test import BacktraderPerformanceTest
from .freqtrade_test import FreqtradePerformanceTest
from .test_runner import PerformanceTestRunner
from .report_generator import ReportGenerator

__all__ = [
    'BasePerformanceTest',
    'PerformanceMetrics',
    'QuantCellPerformanceTest',
    'BacktraderPerformanceTest',
    'FreqtradePerformanceTest',
    'PerformanceTestRunner',
    'ReportGenerator',
]
