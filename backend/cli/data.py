#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据管理命令行工具

提供K线数据下载、导入导出、质量管理等功能。
此模块为入口转发文件，实际功能实现在 scripts.data_cli 模块中。

使用方式: uv run python -m cli.data <命令>

示例:
    uv run python -m cli.data download --symbol BTCUSDT --interval 1h
    uv run python -m cli.data export csv --symbol BTCUSDT --interval 1h --output btc.csv
"""

import sys
from pathlib import Path

backend_path = Path(__file__).resolve().parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))


def main():
    from scripts.data_cli import app
    app()


if __name__ == '__main__':
    main()