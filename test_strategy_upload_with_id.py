#!/usr/bin/env python3
# 测试策略上传功能，支持id参数

import requests
import json

# 读取策略文件内容
with open('/Users/liupeng/workspace/qbot/test_strategy.py', 'r') as f:
    file_content = f.read()

# 测试1: 不带id参数，创建新策略
print("=== 测试1: 不带id参数，创建新策略 ===")
try:
    request_data = {
        "strategy_name": "test_strategy_with_id",
        "file_content": file_content,
        "description": "Test Strategy with ID"
    }
    
    response = requests.post(
        'http://localhost:8000/api/strategy/upload',
        headers={'Content-Type': 'application/json'},
        data=json.dumps(request_data)
    )
    
    print(f"Response Status Code: {response.status_code}")
    print(f"Response Text: {response.text}")
    
    # 查询数据库，获取创建的策略ID
    if response.status_code == 200:
        import sqlite3
        conn = sqlite3.connect('/Users/liupeng/workspace/qbot/backend/data/qbot_sqlite.db')
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM strategies WHERE name = 'test_strategy_with_id'")
        strategy = cursor.fetchone()
        conn.close()
        
        if strategy:
            strategy_id = strategy[0]
            print(f"\n创建的策略ID: {strategy_id}")
            
            # 测试2: 带id参数，更新现有策略
            print("\n=== 测试2: 带id参数，更新现有策略 ===")
            
            # 修改策略文件内容，用于测试更新
            updated_file_content = file_content.replace("This is a test strategy", "This is an updated test strategy")
            
            request_data = {
                "id": strategy_id,
                "strategy_name": "test_strategy_with_id",
                "file_content": updated_file_content,
                "description": "Updated Test Strategy with ID"
            }
            
            response = requests.post(
                'http://localhost:8000/api/strategy/upload',
                headers={'Content-Type': 'application/json'},
                data=json.dumps(request_data)
            )
            
            print(f"Response Status Code: {response.status_code}")
            print(f"Response Text: {response.text}")
            
            # 验证数据库中的策略是否已更新
            if response.status_code == 200:
                conn = sqlite3.connect('/Users/liupeng/workspace/qbot/backend/data/qbot_sqlite.db')
                cursor = conn.cursor()
                cursor.execute("SELECT description FROM strategies WHERE id = ?", (strategy_id,))
                updated_strategy = cursor.fetchone()
                conn.close()
                
                if updated_strategy:
                    print(f"\n更新后的策略描述: {updated_strategy[0]}")
                    if "Updated" in updated_strategy[0]:
                        print("测试成功: 策略已成功更新")
                    else:
                        print("测试失败: 策略未更新")
                else:
                    print("测试失败: 未找到更新后的策略")
            else:
                print("测试失败: 更新策略请求失败")
        else:
            print("测试失败: 未找到创建的策略")
    else:
        print("测试失败: 创建策略请求失败")
        
except Exception as e:
    print(f"测试失败: {e}")
