#!/usr/bin/env python3
"""
数据库迁移脚本

用于在数据库表结构变更时执行迁移操作，避免删除数据库文件。

使用方法:
    cd backend && uv run python scripts/migrate_db.py
"""

import sqlite3
import sys
from pathlib import Path


def get_db_path() -> Path:
    """获取数据库文件路径"""
    project_root = Path(__file__).parent.parent
    db_path = project_root / "data" / "quantcell_sqlite.db"
    if db_path.exists():
        return db_path

    db_path = Path("data/quantcell_sqlite.db")
    if db_path.exists():
        return db_path

    db_path = Path("../data/quantcell_sqlite.db")
    if db_path.exists():
        return db_path

    raise FileNotFoundError("未找到数据库文件")


def check_column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    """检查表中是否已存在指定列"""
    cursor = conn.execute(f"PRAGMA table_info({table})")
    columns = [row[1] for row in cursor.fetchall()]
    return column in columns


def migrate_strategies_table(conn: sqlite3.Connection) -> bool:
    """
    迁移 strategies 表

    变更内容:
    - 添加 parameters 列 (Text, nullable)
    """
    if check_column_exists(conn, "strategies", "parameters"):
        print("[INFO] strategies.parameters 列已存在，跳过迁移")
        return False

    conn.execute("ALTER TABLE strategies ADD COLUMN parameters TEXT")
    conn.commit()
    print("[INFO] strategies.parameters 列添加成功")
    return True


def main():
    """主函数"""
    try:
        db_path = get_db_path()
        print(f"[INFO] 数据库路径: {db_path}")

        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA foreign_keys = ON")

        migrated = False

        if migrate_strategies_table(conn):
            migrated = True

        conn.close()

        if migrated:
            print("[INFO] 数据库迁移完成")
        else:
            print("[INFO] 数据库无需迁移")

        return 0

    except FileNotFoundError as e:
        print(f"[ERROR] 数据库文件未找到: {e}")
        return 1
    except sqlite3.Error as e:
        print(f"[ERROR] 数据库操作失败: {e}")
        return 1
    except Exception as e:
        print(f"[ERROR] 迁移失败: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
