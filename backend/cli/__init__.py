#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QuantCell 命令行工具统一入口

提供回测、策略、数据等子命令的统一入口。
使用方式: uv run python -m cli.<模块名> <命令>

示例:
    uv run python -m cli.backtest run --strategy sma_cross_strategy --symbols BTCUSDT --timeframes 1h
    uv run python -m cli.strategy list
    uv run python -m cli.data download --symbol BTCUSDT --interval 1h
"""

import sys
from pathlib import Path

backend_path = Path(__file__).resolve().parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))
