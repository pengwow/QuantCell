import duckdb
import os
import shutil

def migrate_db(sqlite_path, duckdb_path):
    # 创建目标目录
    os.makedirs(os.path.dirname(duckdb_path), exist_ok=True)
    
    # 连接数据库
    con = duckdb.connect(duckdb_path)
    
    try:
        # 附加SQLite数据库
        con.execute(f"ATTACH '{sqlite_path}' AS source")
        
        # 获取表列表
        tables = con.execute("SELECT name FROM main.sqlite_master WHERE type='table'").fetchall()
        
        # 复制表结构与数据
        for table in tables:
            table_name = table[0]
            con.execute(f"""
            CREATE TABLE {table_name} AS 
            SELECT * FROM source.{table_name} 
            WITH NO DATA
            """)
            con.execute(f"INSERT INTO {table_name} SELECT * FROM source.{table_name}")
        
        print("✅ 迁移完成")
    except Exception as e:
        print(f"❌ 错误: {str(e)}")
    finally:
        con.close()

# 使用示例
migrate_db("/Users/liupeng/workspace/qbot/backend/data/qbot_sqlite.db", "/Users/liupeng/workspace/qbot/backend/data/qbot.db")