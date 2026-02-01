#!/usr/bin/env python3
"""
检查system_config表结构
"""

# 添加项目根目录到Python路径
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from collector.db.database import init_database_config, SessionLocal
from sqlalchemy import text

# 初始化数据库配置
init_database_config()

# 查询system_config表结构
with SessionLocal() as session:
    try:
        # 获取数据库类型
        from collector.db.database import db_type
        
        if db_type == "sqlite":
            # SQLite: 使用PRAGMA table_info查询表结构
            result = session.execute(
                text("PRAGMA table_info(system_config)")
            )
            columns = result.fetchall()
            
            print("system_config表结构 (SQLite):")
            print("=" * 50)
            for column in columns:
                print(f"列名: {column.name}, 类型: {column.type}, 非空: {column.notnull}, 默认值: {column.dflt_value}, 主键: {column.pk}")
        elif db_type == "duckdb":
            # DuckDB: 使用information_schema.columns查询表结构
            result = session.execute(
                text("SELECT column_name, data_type, is_nullable, column_default, column_key FROM information_schema.columns WHERE table_name = 'system_config'")
            )
            columns = result.fetchall()
            
            print("system_config表结构 (DuckDB):")
            print("=" * 50)
            for column in columns:
                print(f"列名: {column.column_name}, 类型: {column.data_type}, 非空: {column.is_nullable}, 默认值: {column.column_default}, 主键: {column.column_key}")
        
        print("=" * 50)
    except Exception as e:
        print(f"查询表结构失败: {e}")
