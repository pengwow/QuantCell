#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent 管理命令行工具(兼容 shim)

已迁移到 ``quantcell agent`` 子命令,此文件仅作为 6 个月兼容期转发。
新代码请直接使用:

    quantcell agent --help
    python -m cli.run agent --help

或继续使用本 shim(行为完全一致)。
"""


def main() -> None:
    """shim 入口 — 转发到 cli.agent.app"""
    from cli.agent import app
    app()


if __name__ == "__main__":
    main()
