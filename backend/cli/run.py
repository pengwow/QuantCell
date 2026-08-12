"""CLI 入口点 — 被 pyproject.toml 注册为 ``quantcell`` 命令。

``quantcell`` = ``python -m cli.run``

平迁完成后,12 个 scripts/xxx_cli.py 仍能用(改 shim 转调 cli.<name>),
6 个月后删除 scripts/ 时,只需把 shim 移除即可,不影响 cli 入口。
"""
from __future__ import annotations

import sys
from pathlib import Path

backend_path = Path(__file__).resolve().parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from cli import app, register_commands


def cli() -> None:
    """Console entry point,registered as ``quantcell`` in pyproject."""
    register_commands()
    app()


if __name__ == "__main__":
    cli()
