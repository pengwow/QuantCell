"""quantcell migrate — 数据库迁移。

原 ``scripts/migrate_db.py`` 不是 typer 结构(裸 ``main() + sys.exit``),
这里薄包一层 typer 接口,行为完全一致。
"""
from __future__ import annotations

import sys
import importlib.util
from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(
    name="migrate",
    help="数据库迁移(SQLite schema 升级)",
    add_completion=False,
    invoke_without_command=True,
)


def _load_migrate_main():
    """加载 scripts/migrate_db.py 的 main 函数"""
    backend_dir = Path(__file__).resolve().parent.parent
    migrate_script = backend_dir / "scripts" / "migrate_db.py"

    spec = importlib.util.spec_from_file_location("migrate_db", str(migrate_script))
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载迁移脚本: {migrate_script}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.main


@app.callback(invoke_without_command=True)
def migrate_main(
    ctx: typer.Context,
    confirm: bool = typer.Option(False, "--yes", "-y", help="跳过确认提示"),
):
    """执行数据库迁移。"""
    if ctx.invoked_subcommand is not None:
        return

    if not confirm:
        typer.confirm("确认执行数据库迁移?", abort=True)

    _migrate_main = _load_migrate_main()
    rc = _migrate_main()
    sys.exit(rc or 0)
