#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
回测命令行工具(兼容 shim)

已迁移到 ``quantcell backtest`` 子命令,此文件仅作为兼容期转发。
新代码请直接使用:

    quantcell backtest --help
"""
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


def main() -> None:
    from backtest.cli import app
    app()


if __name__ == '__main__':
    main()
