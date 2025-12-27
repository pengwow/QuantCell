import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath('.'))

from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy import create_engine

# 数据库连接URL（使用DuckDB）
db_url = "duckdb:////Users/liupeng/workspace/qbot/backend/data/qbot.db"

# 创建引擎
engine = create_engine(db_url)

print("连接到数据库...")

# 使用Session执行迁移
with Session(engine) as session:
    # 检查data_pool_assets表的结构
    print("\n检查data_pool_assets表的结构...")
    columns = session.execute(text("DESCRIBE data_pool_assets")).fetchall()
    column_names = [column[0] for column in columns]
    
    print("当前表结构:")
    for column in columns:
        print(f"{column[0]} | {column[1]} | {column[2]} | {column[3]}")
    
    # 检查是否已经有id列
    if "id" not in column_names:
        print("\n执行迁移：在data_pool_assets表中添加id字段...")
        try:
            # 对于DuckDB，我们使用临时表的方式来添加自增主键
            
            # 1. 创建临时表，包含原有数据和自动生成的id
            session.execute(text("""
                CREATE TABLE temp_data_pool_assets AS 
                SELECT 
                    row_number() OVER () AS id,
                    pool_id,
                    asset_id,
                    asset_type,
                    created_at,
                    updated_at
                FROM data_pool_assets
            """))
            
            # 2. 删除原表
            session.execute(text("DROP TABLE data_pool_assets"))
            
            # 3. 将临时表重命名为原表
            session.execute(text("ALTER TABLE temp_data_pool_assets RENAME TO data_pool_assets"))
            
            # 4. 设置id为主键
            session.execute(text("ALTER TABLE data_pool_assets ADD PRIMARY KEY (id)"))
            
            session.commit()
            print("迁移成功：已在data_pool_assets表中添加id自增主键")
        except Exception as e:
            session.rollback()
            print(f"迁移失败: {e}")
    else:
        print("\ndata_pool_assets表已经有id列，无需迁移")
    
    # 再次检查表结构
    print("\n更新后的表结构:")
    columns = session.execute(text("DESCRIBE data_pool_assets")).fetchall()
    for column in columns:
        print(f"{column[0]} | {column[1]} | {column[2]} | {column[3]}")
