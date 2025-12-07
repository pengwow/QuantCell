import duckdb
import pandas as pd

db_path = '/Users/liupeng/workspace/qbot/backend/data/qbot.db'
conn = duckdb.connect(str(db_path))
df = conn.execute("SELECT * FROM klines LIMIT 10;").df()
print(df.head())
# 直接读取CSV/Parquet文件到DataFrame
# df = duckdb.sql("tables").df()
# print(df.head())


