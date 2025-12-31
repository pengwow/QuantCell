#!/usr/bin/env python3
# 测试/api/data/crypto/symbols接口

import json

import requests


# 测试接口
def test_crypto_symbols_api():
    print("开始测试/api/data/crypto/symbols接口...")
    
    # API地址
    base_url = "http://localhost:8001"
    api_url = f"{base_url}/api/data/crypto/symbols"
    
    # 测试参数
    test_cases = [
        # 测试默认参数
        {},
        # 测试不同交易所
        {"exchange": "binance"},
        # 测试过滤功能
        {"exchange": "binance", "filter": "USDT"},
        {"exchange": "binance", "filter": "BTC"},
        # 测试分页功能
        {"exchange": "binance", "limit": 5},
        {"exchange": "binance", "limit": 5, "offset": 5},
        # 测试其他交易所
        {"exchange": "okx"},
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
                    symbols_data = data.get("data")
                    if symbols_data:
                        symbols = symbols_data.get("symbols")
                        if symbols:
                            print(f"✅ 测试通过！获取到货币对列表，交易所: {symbols_data.get('exchange')}, 数量: {len(symbols)}, 总数量: {symbols_data.get('total')}")
                        else:
                            print(f"❌ 测试失败！响应数据中没有货币对列表")
                    else:
                        print(f"❌ 测试失败！响应数据中没有symbols_data")
                else:
                    print(f"❌ 测试失败！响应码不为0，错误信息: {data.get('message')}")
            else:
                print(f"❌ 测试失败！响应状态码不为200")
                print(f"响应内容: {response.text}")
        except Exception as e:
            print(f"❌ 测试失败！出现异常: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    test_crypto_symbols_api()