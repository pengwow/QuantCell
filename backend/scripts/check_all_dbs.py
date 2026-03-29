#!/usr/bin/env python3
"""
检查所有数据库文件的 workers 表结构
"""

import sqlite3
from pathlib import Path

# 所有可能的数据库文件路径
db_paths = [
    Path("/Users/liupeng/workspace/quant/QuantCell/backend/data/quantcell_sqlite.db"),
    Path("/Users/liupeng/workspace/quant/QuantCell/backend/quant_cell.db"),
    Path("/Users/liupeng/workspace/quant/QuantCell/backend/scripts/quant_cell.db"),
    Path("/Users/liupeng/workspace/quant/QuantCell/quant_cell.db"),
]


def check_db(db_path: Path):
    """检查数据库文件的 workers 表结构"""
    print(f"\n{'='*60}")
    print(f"数据库: {db_path}")
    print(f"{'='*60}")

    if not db_path.exists():
        print("  文件不存在")
        return

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 检查 workers 表是否存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='workers'")
        if not cursor.fetchone():
            print("  workers 表不存在")
            conn.close()
            return

        # 获取表结构
        cursor.execute("PRAGMA table_info(workers)")
        columns = cursor.fetchall()

        print(f"  列数: {len(columns)}")
        print("  列详情:")

        # 需要检查的旧列
        old_columns = {'exchange', 'symbol', 'timeframe', 'market_type', 'trading_mode'}
        found_old = []

        for col in columns:
            # col: (cid, name, type, notnull, dflt_value, pk)
            cid, name, col_type, notnull, dflt_value, pk = col
            nullable = "NOT NULL" if notnull else "NULL"
            pk_str = " PRIMARY KEY" if pk else ""
            default_str = f" DEFAULT {dflt_value}" if dflt_value is not None else ""

            marker = ""
            if name in old_columns:
                marker = " ⚠️ 旧列"
                found_old.append(name)

            print(f"    - {name}: {col_type} ({nullable}){pk_str}{default_str}{marker}")

        if found_old:
            print(f"\n  ⚠️ 发现旧列: {found_old}")
            print("  这些列应该被删除，请运行 fix_worker_table_columns.py 修复")
        else:
            print("\n  ✅ 没有旧列，表结构正确")

        conn.close()

    except Exception as e:
        print(f"  错误: {e}")


if __name__ == "__main__":
    print("检查所有数据库文件的 workers 表结构...")

    for db_path in db_paths:
        check_db(db_path)

    print("\n" + "="*60)
    print("检查完成")
    print("="*60)
