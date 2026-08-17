#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
策略管理命令行工具

提供策略的增删改查、生成、分析、优化、诊断、部署等功能。
此模块为入口转发文件，实际功能实现在 scripts.strategy_cli 模块中。

使用方式: uv run python -m cli.strategy <命令>

示例:
    uv run python -m cli.strategy list
    uv run python -m cli.strategy generate --requirement "双均线交叉策略" --name sma_cross
"""

import sys
from pathlib import Path

backend_path = Path(__file__).resolve().parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))


def main():
    from scripts.strategy_cli import app
    app()


if __name__ == '__main__':
    main()