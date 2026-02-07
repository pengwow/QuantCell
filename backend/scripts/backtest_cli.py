#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QUANTCELL 回测命令行工具入口

此文件为入口转发文件，实际功能实现在 backtest.cli 模块中
"""

import sys
from pathlib import Path

# 添加后端目录到路径
backend_path = Path(__file__).resolve().parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

# 从新模块导入并运行
from backtest.cli import app

if __name__ == '__main__':
    app()
