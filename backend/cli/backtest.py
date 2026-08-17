#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
回测命令行工具

此模块为入口转发文件，实际功能实现在 backtest.cli 模块中。
使用方式: uv run python -m cli.backtest <命令>

示例:
    uv run python -m cli.backtest run --strategy sma_cross_strategy --symbols BTCUSDT --timeframes 1h
    uv run python -m cli.backtest list-strategies
"""

import sys
from pathlib import Path

backend_path = Path(__file__).resolve().parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))


def main():
    from backtest.cli import app
    app()


if __name__ == '__main__':
    main()
