"""quantcell migrate — 数据库迁移。

原 ``scripts/migrate_db.py`` 不是 typer 结构(裸 ``main() + sys.exit``),
这里薄包一层 typer 接口,行为完全一致。
"""
from __future__ import annotations

import sys
from typing import Optional

import typer

# 走原 scripts/migrate_db 的 main() 函数(零业务重写)
from scripts.migrate_db import main as _migrate_main

app = typer.Typer(
    name="migrate",
    help="数据库迁移(SQLite schema 升级)",
    add_completion=False,
)


@app.command("run")
def migrate_run(
    confirm: bool = typer.Option(False, "--yes", "-y", help="跳过确认提示"),
) -> None:
    """执行数据库迁移。"""
    if not confirm:
        typer.confirm("确认执行数据库迁移?", abort=True)
    rc = _migrate_main()
    sys.exit(rc or 0)
