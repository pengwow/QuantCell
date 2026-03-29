#!/usr/bin/env python3
"""
修复 workers 表结构 - 删除旧的交易配置列

由于 SQLite 不支持直接删除列，我们需要：
1. 创建新表（不包含旧列）
2. 复制数据
3. 删除旧表
4. 重命名新表
"""

import sqlite3
import sys
from pathlib import Path

# 数据库文件路径
db_path = Path(__file__).parent.parent / "data" / "quantcell_sqlite.db"


def fix_workers_table():
    """修复 workers 表，删除旧的交易配置列"""
    if not db_path.exists():
        print(f"数据库文件不存在: {db_path}")
        return False

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # 检查 workers 表是否存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='workers'")
        if not cursor.fetchone():
            print("workers 表不存在")
            return False

        # 获取现有列
        cursor.execute("PRAGMA table_info(workers)")
        columns = {row[1]: row for row in cursor.fetchall()}

        print(f"现有列: {list(columns.keys())}")

        # 需要删除的旧列
        old_columns = ['exchange', 'symbol', 'timeframe', 'market_type', 'trading_mode']
        columns_to_remove = [col for col in old_columns if col in columns]

        if not columns_to_remove:
            print("没有需要删除的旧列")
            return True

        print(f"需要删除的列: {columns_to_remove}")

        # 获取要保留的列（排除旧列）
        keep_columns = [col for col in columns.keys() if col not in old_columns]
        print(f"保留的列: {keep_columns}")

        # 构建新表的列定义
        column_defs = []
        for col_name in keep_columns:
            col_info = columns[col_name]
            # col_info: (cid, name, type, notnull, dflt_value, pk)
            col_def = f"{col_info[1]} {col_info[2]}"
            if col_info[3]:  # notnull
                col_def += " NOT NULL"
            if col_info[4] is not None:  # default value
                col_def += f" DEFAULT {col_info[4]}"
            if col_info[5]:  # primary key
                col_def += " PRIMARY KEY"
            column_defs.append(col_def)

        # 开始事务
        conn.execute("BEGIN TRANSACTION")

        # 1. 创建新表
        new_table_name = "workers_new"
        create_sql = f"CREATE TABLE {new_table_name} ({', '.join(column_defs)})"
        print(f"创建新表 SQL: {create_sql}")
        cursor.execute(create_sql)

        # 2. 复制数据
        columns_str = ', '.join(keep_columns)
        insert_sql = f"INSERT INTO {new_table_name} ({columns_str}) SELECT {columns_str} FROM workers"
        print(f"复制数据 SQL: {insert_sql}")
        cursor.execute(insert_sql)

        # 3. 删除旧表
        cursor.execute("DROP TABLE workers")

        # 4. 重命名新表
        cursor.execute(f"ALTER TABLE {new_table_name} RENAME TO workers")

        # 5. 重新创建索引
        # 获取现有索引
        cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='workers'")
        # 注意：由于我们已经删除了旧表，索引也已经不存在了
        # 需要手动创建必要的索引

        # 创建必要的索引
        indexes = [
            "CREATE UNIQUE INDEX IF NOT EXISTS unique_worker_name ON workers(name)",
            "CREATE INDEX IF NOT EXISTS idx_worker_status ON workers(status)",
            "CREATE INDEX IF NOT EXISTS idx_worker_strategy ON workers(strategy_id)",
        ]

        for idx_sql in indexes:
            try:
                cursor.execute(idx_sql)
                print(f"创建索引: {idx_sql}")
            except sqlite3.OperationalError as e:
                print(f"创建索引失败（可能已存在）: {e}")

        conn.commit()
        print("✅ workers 表修复完成")
        return True

    except Exception as e:
        conn.rollback()
        print(f"❌ 修复失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        conn.close()


if __name__ == "__main__":
    success = fix_workers_table()
    sys.exit(0 if success else 1)
