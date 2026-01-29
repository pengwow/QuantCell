#!/usr/bin/env python3
# 测试策略上传功能

import requests
import json

# 读取策略文件内容
with open('/Users/liupeng/workspace/quantcell/test_strategy.py', 'r') as f:
    file_content = f.read()

# 构建请求数据
request_data = {
    "strategy_name": "test_strategy",
    "file_content": file_content,
    "description": "Test Strategy Description"
}

# 发送请求
try:
    response = requests.post(
        'http://localhost:8000/api/strategy/upload',
        headers={'Content-Type': 'application/json'},
        data=json.dumps(request_data)
    )
    
    # 打印响应结果
    print(f"Response Status Code: {response.status_code}")
    print(f"Response Text: {response.text}")
    
    # 如果响应成功，检查策略是否保存到数据库
    if response.status_code == 200:
        import sqlite3
        
        # 连接数据库
        conn = sqlite3.connect('/Users/liupeng/workspace/quantcell/backend/data/quantcell_sqlite.db')
        cursor = conn.cursor()
        
        # 查询策略信息
        cursor.execute("SELECT * FROM strategies WHERE name = 'test_strategy'")
        strategy = cursor.fetchone()
        
        if strategy:
            print("\n策略已成功保存到数据库:")
            print(f"策略名称: {strategy[0]}")
            print(f"文件名: {strategy[1]}")
            print(f"描述: {strategy[2]}")
            print(f"参数: {strategy[3]}")
            print(f"创建时间: {strategy[4]}")
            print(f"更新时间: {strategy[5]}")
        else:
            print("\n策略未保存到数据库")
        
        # 关闭数据库连接
        conn.close()
        
except Exception as e:
    print(f"测试失败: {e}")
