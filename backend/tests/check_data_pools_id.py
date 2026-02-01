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

# 使用Session检查data_pools表的id字段定义
with Session(engine) as session:
    # 检查data_pools表的结构，特别是id字段
    print("\n检查data_pools表的id字段定义...")
    try:
        # 使用DuckDB的DESCRIBE命令检查表结构
        columns = session.execute(text("DESCRIBE data_pools")).fetchall()
        
        print("列名 | 数据类型 | 空值 | 默认值")
        print("-" * 60)
        for column in columns:
            print(f"{column[0]} | {column[1]} | {column[2]} | {column[3]}")
        
        # 尝试手动插入一条记录，看看id是否会自动生成
        print("\n尝试手动插入一条记录...")
        result = session.execute(text("""
            INSERT INTO data_pools (name, type, description, color, tags, is_public, is_default)
            VALUES ('测试资产池', 'crypto', '这是一个测试资产池', '#FF0000', '["test", "crypto"]', TRUE, FALSE)
            RETURNING id
        """))
        inserted_id = result.fetchone()[0]
        session.commit()
        print(f"成功插入记录，自动生成的id: {inserted_id}")
        
        # 清理测试数据
        session.execute(text(f"DELETE FROM data_pools WHERE id = {inserted_id}"))
        session.commit()
        print("清理测试数据成功")
    except Exception as e:
        session.rollback()
        print(f"检查或插入失败: {e}")
