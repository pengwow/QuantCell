#!/usr/bin/env python3
# 测试/api/data/calendars接口

import json

import requests


# 测试接口
def test_calendars_api():
    print("开始测试/api/data/calendars接口...")
    
    # API地址
    base_url = "http://localhost:8001"
    api_url = f"{base_url}/api/data/calendars"
    
    # 测试参数
    test_cases = [
        # 测试默认频率
        {},
        # 测试指定频率
        {"freq": "1d"},
        {"freq": "day"},
        {"freq": "1h"},
        {"freq": "5m"},
    ]
    
    for i, params in enumerate(test_cases):
        print(f"\n测试用例 {i+1}: {params}")
        
        try:
            # 发送请求
            response = requests.get(api_url, params=params)
            print(f"请求URL: {response.url}")
            print(f"响应状态码: {response.status_code}")
            
            # 检查响应状态码
            if response.status_code == 200:
                # 解析响应数据
                data = response.json()
                print(f"响应数据: {json.dumps(data, indent=2, ensure_ascii=False)}")
                
                # 检查响应结构
                if data.get("code") == 0:
                    calendar_data = data.get("data")
                    if calendar_data:
                        print(f"✅ 测试通过！获取到交易日历，频率: {calendar_data.get('freq')}, 交易日数量: {calendar_data.get('count')}")
                    else:
                        print(f"❌ 测试失败！响应数据中没有日历信息")
                else:
                    print(f"❌ 测试失败！响应码不为0，错误信息: {data.get('message')}")
            else:
                print(f"❌ 测试失败！响应状态码不为200")
                print(f"响应内容: {response.text}")
        except Exception as e:
            print(f"❌ 测试失败！出现异常: {e}")

if __name__ == "__main__":
    test_calendars_api()