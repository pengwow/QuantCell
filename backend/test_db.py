# 测试数据库连接和查询

from collector.db import get_db_connection, SystemConfig

# 测试数据库连接
conn = get_db_connection()
print("数据库连接成功")

# 查询系统配置表
print("\n查询系统配置表:")
cursor = conn.execute("SELECT * FROM system_config")
rows = cursor.fetchall()
print(f"共 {len(rows)} 条记录")
for row in rows:
    print(row)

# 测试SystemConfig类
print("\n测试SystemConfig.get_all():")
configs = SystemConfig.get_all()
print(f"共 {len(configs)} 条配置")
for key, value in configs.items():
    print(f"{key}: {value}")
