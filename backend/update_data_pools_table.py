import sys
import os
import json

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath('.'))

from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy import create_engine

# 数据库连接URL（假设使用DuckDB）
db_url = "duckdb:////Users/liupeng/workspace/qbot/backend/data/qbot.db"

# 创建引擎
engine = create_engine(db_url)

print("连接到数据库...")

# 使用Session更新表结构
with Session(engine) as session:
    # 更新data_pools表，添加缺少的列
    print("\n更新data_pools表，添加缺少的列...")
    
    # 检查并添加is_public列
    try:
        session.execute(text("ALTER TABLE data_pools ADD COLUMN is_public BOOLEAN DEFAULT TRUE"))
        session.commit()
        print("添加is_public列成功")
    except Exception as e:
        session.rollback()
        print(f"添加is_public列失败: {e}")
    
    # 检查并添加is_default列
    try:
        session.execute(text("ALTER TABLE data_pools ADD COLUMN is_default BOOLEAN DEFAULT FALSE"))
        session.commit()
        print("添加is_default列成功")
    except Exception as e:
        session.rollback()
        print(f"添加is_default列失败: {e}")
    
    # 更新data_pool_assets表，添加缺少的列
    print("\n更新data_pool_assets表，添加缺少的列...")
    
    # 检查并添加id列
    try:
        session.execute(text("ALTER TABLE data_pool_assets ADD COLUMN id INTEGER PRIMARY KEY"))
        session.commit()
        print("添加id列成功")
    except Exception as e:
        session.rollback()
        print(f"添加id列失败: {e}")
    
    # 检查并添加updated_at列
    try:
        session.execute(text("ALTER TABLE data_pool_assets ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"))
        session.commit()
        print("添加updated_at列成功")
    except Exception as e:
        session.rollback()
        print(f"添加updated_at列失败: {e}")
    
    # 再次检查data_pools表的结构
    print("\n再次检查data_pools表的结构:")
    columns = session.execute(text("DESCRIBE data_pools")).fetchall()
    print("列名 | 数据类型 | 空值 | 默认值")
    print("-" * 60)
    for column in columns:
        print(f"{column[0]} | {column[1]} | {column[2]} | {column[3]}")
    
    # 再次检查data_pool_assets表的结构
    print("\n再次检查data_pool_assets表的结构:")
    columns = session.execute(text("DESCRIBE data_pool_assets")).fetchall()
    print("列名 | 数据类型 | 空值 | 默认值")
    print("-" * 60)
    for column in columns:
        print(f"{column[0]} | {column[1]} | {column[2]} | {column[3]}")
