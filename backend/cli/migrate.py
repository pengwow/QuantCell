"""quantcell migrate — 数据库迁移。

将原 scripts/migrate_db.py 的实现直接内联,不再动态加载。
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import typer

backend_dir = Path(__file__).resolve().parent.parent
app = typer.Typer(
    name="migrate",
    help="数据库迁移(SQLite schema 升级)",
    add_completion=False,
    invoke_without_command=True,
)


def get_db_path() -> Path:
    """获取数据库文件路径"""
    _backend_dir = Path(__file__).parent.parent
    candidates = [
        _backend_dir / "data" / "quantcell_sqlite.db",
        Path("data/quantcell_sqlite.db"),
        Path("../data/quantcell_sqlite.db"),
    ]
    for db_path in candidates:
        if db_path.exists():
            return db_path
    msg = "未找到数据库文件"
    raise FileNotFoundError(msg)


def check_column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cursor = conn.execute(f"PRAGMA table_info({table})")
    columns = [row[1] for row in cursor.fetchall()]
    return column in columns


def migrate_strategies_table(conn: sqlite3.Connection) -> bool:
    if check_column_exists(conn, "strategies", "parameters"):
        typer.echo("[INFO] strategies.parameters 列已存在，跳过迁移")
        return False
    conn.execute("ALTER TABLE strategies ADD COLUMN parameters TEXT")
    conn.commit()
    typer.echo("[INFO] strategies.parameters 列添加成功")
    return True


def _run_migration() -> int:
    try:
        db_path = get_db_path()
        typer.echo(f"[INFO] 数据库路径: {db_path}")

        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA foreign_keys = ON")

        migrated = False
        if migrate_strategies_table(conn):
            migrated = True

        conn.close()

        if migrated:
            typer.echo("[INFO] 数据库迁移完成")
        else:
            typer.echo("[INFO] 数据库无需迁移")
        return 0

    except FileNotFoundError as e:
        typer.echo(f"[ERROR] 数据库文件未找到: {e}", err=True)
        return 1
    except sqlite3.Error as e:
        typer.echo(f"[ERROR] 数据库操作失败: {e}", err=True)
        return 1
    except Exception as e:
        typer.echo(f"[ERROR] 迁移失败: {e}", err=True)
        return 1


def main():
    """CLI 入口函数"""
    return _run_migration()


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
    sys.exit(_run_migration() or 0)
