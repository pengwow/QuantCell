#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据管理命令行工具(兼容 shim)

已迁移到 ``quantcell data`` 子命令,此文件仅作为 6 个月兼容期转发。
新代码请直接使用:

    quantcell data --help
    python -m cli.run data --help

或继续使用本 shim(行为完全一致)。
"""
import sys
from pathlib import Path

# 添加后端目录到路径(原 scripts 的行为,保留无害)
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


def main() -> None:
    """shim 入口 — 转发到 cli.data.app"""
    from cli.data import app
    app()


if __name__ == "__main__":
    main()
