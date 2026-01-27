#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
修复数据库表结构，添加缺失的data_source列
"""

import sys
import os
from pathlib import Path
import sqlite3

# 数据库文件路径
db_file = Path(__file__).parent / "backend" / "data" / "qbot_sqlite.db"

print(f"数据库文件路径: {db_file}")
print(f"数据库文件是否存在: {db_file.exists()}")

if not db_file.exists():
    print("数据库文件不存在，退出修复！")
    sys.exit(1)

# 连接到数据库
conn = sqlite3.connect(str(db_file))
cursor = conn.cursor()

try:
    # 检查表是否存在
    print("\n检查crypto_spot_klines表是否存在...")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='crypto_spot_klines'")
    table_exists = cursor.fetchone()
    
    if not table_exists:
        print("crypto_spot_klines表不存在，跳过修复")
        sys.exit(0)
    
    print("crypto_spot_klines表存在")
    
    # 检查data_source列是否存在
    print("\n检查data_source列是否存在...")
    cursor.execute("PRAGMA table_info(crypto_spot_klines)")
    columns = cursor.fetchall()
    
    column_names = [col[1] for col in columns]
    print(f"当前表的列: {column_names}")
    
    if 'data_source' in column_names:
        print("data_source列已存在，跳过修复")
        sys.exit(0)
    
    print("data_source列不存在，开始添加...")
    
    # 添加data_source列
    cursor.execute("ALTER TABLE crypto_spot_klines ADD COLUMN data_source VARCHAR(50) NOT NULL DEFAULT 'unknown'")
    print("data_source列添加成功！")
    
    # 创建索引
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_crypto_spot_klines_data_source ON crypto_spot_klines(data_source)")
    print("索引创建成功！")
    
    # 提交更改
    conn.commit()
    
    print("\ncrypto_spot_klines表修复完成！")
    
    # 验证修复结果
    print("\n验证修复结果...")
    cursor.execute("PRAGMA table_info(crypto_spot_klines)")
    columns = cursor.fetchall()
    column_names = [col[1] for col in columns]
    
    if 'data_source' in column_names:
        print("✓ data_source列已成功添加")
    else:
        print("✗ data_source列添加失败")
    
    # 测试查询
    print("\n测试查询K线数据...")
    try:
        cursor.execute("SELECT COUNT(*) FROM crypto_spot_klines")
        count = cursor.fetchone()[0]
        print(f"✓ K线数据查询成功，共 {count} 条记录")
    except Exception as e:
        print(f"✗ K线数据查询失败: {e}")
    
except Exception as e:
    print(f"\n修复失败: {e}")
    import traceback
    traceback.print_exc()
    conn.rollback()
finally:
    conn.close()

print("\n修复完成！")