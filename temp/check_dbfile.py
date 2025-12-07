import os
import sqlite3
import duckdb

def detect_database_type(file_path):
    if not os.path.isfile(file_path):
        return "❌ 文件不存在"

    # 方法1：文件头检测
    with open(file_path, 'rb') as f:
        header = f.read(32)
        if header.startswith(b"SQLite format 3"):
            return "✅ SQLite 数据库"
    
    # 方法2：SQLite连接验证
    try:
        conn = sqlite3.connect(file_path)
        conn.execute("SELECT 1").close()
        conn.close()
        return "✅ SQLite 数据库"
    except sqlite3.DatabaseError:
        pass

    # 方法3：DuckDB连接验证
    try:
        conn = duckdb.connect(file_path)
        conn.close()
        return "✅ DuckDB 数据库"
    except duckdb.Error:
        pass

    return "❌ 未知数据库类型"

# 使用示例
print(detect_database_type("/Users/liupeng/workspace/qbot/backend/data/qbot.db"))
