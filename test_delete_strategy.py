#!/usr/bin/env python3
# 测试删除策略API

import requests
import json

# 读取策略文件内容
with open('/Users/liupeng/workspace/quantcell/test_strategy.py', 'r') as f:
    file_content = f.read()

# 步骤1: 创建测试策略
print("=== 步骤1: 创建测试策略 ===")
try:
    request_data = {
        "strategy_name": "test_delete_strategy",
        "file_content": file_content,
        "description": "Test Strategy for Delete API"
    }
    
    response = requests.post(
        'http://localhost:8000/api/strategy/upload',
        headers={'Content-Type': 'application/json'},
        data=json.dumps(request_data)
    )
    
    print(f"创建策略响应: {response.status_code}")
    print(f"响应内容: {response.text}")
    
    # 步骤2: 获取策略列表，确认策略创建成功
    print("\n=== 步骤2: 获取策略列表 ===")
    response = requests.get('http://localhost:8000/api/strategy/list')
    print(f"策略列表响应: {response.status_code}")
    strategies = response.json()['data']['strategies']
    print(f"当前策略数量: {len(strategies)}")
    for strategy in strategies:
        print(f"  - {strategy['name']}: {strategy['description']}")
    
    # 步骤3: 删除策略
    print("\n=== 步骤3: 删除策略 ===")
    response = requests.delete('http://localhost:8000/api/strategy/test_delete_strategy')
    print(f"删除策略响应: {response.status_code}")
    print(f"响应内容: {response.text}")
    
    # 步骤4: 再次获取策略列表，确认策略已删除
    print("\n=== 步骤4: 再次获取策略列表 ===")
    response = requests.get('http://localhost:8000/api/strategy/list')
    print(f"策略列表响应: {response.status_code}")
    strategies = response.json()['data']['strategies']
    print(f"当前策略数量: {len(strategies)}")
    for strategy in strategies:
        print(f"  - {strategy['name']}: {strategy['description']}")
    
    # 步骤5: 验证策略文件是否已删除
    print("\n=== 步骤5: 验证策略文件是否已删除 ===")
    import os
    strategy_file_path = '/Users/liupeng/workspace/quantcell/backend/strategies/test_delete_strategy.py'
    if os.path.exists(strategy_file_path):
        print(f"❌ 策略文件未被删除: {strategy_file_path}")
    else:
        print(f"✅ 策略文件已成功删除")
    
    print("\n=== 测试完成 ===")
    
except Exception as e:
    print(f"测试失败: {e}")
    import traceback
    traceback.print_exc()
