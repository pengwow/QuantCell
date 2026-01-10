#!/usr/bin/env python3

"""
简单的策略上传测试脚本
"""

import requests
import json

# 上传策略
strategy_name = 'test_simple'
file_content = '''
class TestSimpleStrategy(Strategy):
    """测试简单策略"""
    
    # 参数定义
    param1 = 10  # 参数1
    param2 = 20.5  # 参数2
    
    def next(self):
        if self.param1 > self.param2:
            self.buy()
        else:
            self.sell()
'''

url = 'http://localhost:8000/api/strategy/upload'
headers = {'Content-Type': 'application/json'}
data = {
    'strategy_name': strategy_name,
    'file_content': file_content,
    'description': '测试简单策略上传'
}

print('开始上传策略...')
response = requests.post(url, headers=headers, data=json.dumps(data))
print('上传响应:', response.status_code)
print('上传结果:', response.json())

# 测试获取策略列表
list_url = 'http://localhost:8000/api/strategy/list'
list_response = requests.get(list_url)
print('\n获取策略列表...')
print('列表响应:', list_response.status_code)
list_data = list_response.json()
print('策略数量:', len(list_data['data']['strategies']))
for strategy in list_data['data']['strategies']:
    print('策略:', strategy['name'], '来源:', strategy['source'])
