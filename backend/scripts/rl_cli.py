#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RL 训练命令行工具(兼容 shim)

已迁移到 ``quantcell rl`` 子命令,此文件仅作为 6 个月兼容期转发。
新代码请直接使用:

    quantcell rl --help
    python -m cli.run rl --help

或继续使用本 shim(行为完全一致)。
"""


def main() -> None:
    """shim 入口 — 转发到 cli.rl.app"""
    from cli.rl import app
    app()


if __name__ == "__main__":
    main()
