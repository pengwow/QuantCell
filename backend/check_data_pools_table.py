import sys
import os
import json

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath('.'))

from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy import create_engine

# 数据库连接URL（假设使用DuckDB）
db_url = "duckdb:////Users/liupeng/workspace/quantcell/backend/data/quantcell.db"

# 创建引擎
engine = create_engine(db_url)

print("连接到数据库...")

# 使用Session检查data_pools表的结构
with Session(engine) as session:
    # 检查表是否存在
    print("\n检查data_pools表是否存在...")
    data_pools_exists = session.execute(text("SELECT table_name FROM information_schema.tables WHERE table_name='data_pools'")).fetchone()
    
    print(f"data_pools表存在: {data_pools_exists is not None}")
    
    if data_pools_exists:
        # 检查表的结构
        print("\n检查data_pools表的结构:")
        columns = session.execute(text("DESCRIBE data_pools")).fetchall()
        print("列名 | 数据类型 | 空值 | 默认值")
        print("-" * 60)
        for column in columns:
            print(f"{column[0]} | {column[1]} | {column[2]} | {column[3]}")
        
        # 检查data_pool_assets表是否存在
        print("\n检查data_pool_assets表是否存在...")
        data_pool_assets_exists = session.execute(text("SELECT table_name FROM information_schema.tables WHERE table_name='data_pool_assets'")).fetchone()
        print(f"data_pool_assets表存在: {data_pool_assets_exists is not None}")
        
        if data_pool_assets_exists:
            print("\n检查data_pool_assets表的结构:")
            columns = session.execute(text("DESCRIBE data_pool_assets")).fetchall()
            print("列名 | 数据类型 | 空值 | 默认值")
            print("-" * 60)
            for column in columns:
                print(f"{column[0]} | {column[1]} | {column[2]} | {column[3]}")
    else:
        print("\ndata_pools表不存在，需要创建")
        
        # 创建data_pools表
        print("\n创建data_pools表...")
        try:
            session.execute(text("""
                CREATE TABLE data_pools (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name VARCHAR NOT NULL,
                    type VARCHAR,
                    description TEXT,
                    color VARCHAR,
                    tags TEXT,
                    is_public BOOLEAN DEFAULT TRUE,
                    is_default BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            session.commit()
            print("data_pools表创建成功")
            
            # 创建data_pool_assets表
            print("\n创建data_pool_assets表...")
            session.execute(text("""
                CREATE TABLE data_pool_assets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pool_id INTEGER NOT NULL,
                    asset_id VARCHAR NOT NULL,
                    asset_type VARCHAR NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            session.commit()
            print("data_pool_assets表创建成功")
            
            # 再次检查data_pools表的结构
            print("\n再次检查data_pools表的结构:")
            columns = session.execute(text("DESCRIBE data_pools")).fetchall()
            print("列名 | 数据类型 | 空值 | 默认值")
            print("-" * 60)
            for column in columns:
                print(f"{column[0]} | {column[1]} | {column[2]} | {column[3]}")
        except Exception as e:
            session.rollback()
            print(f"创建表失败: {e}")
