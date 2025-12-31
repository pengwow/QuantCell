import requests
import json

# 测试后端API是否正常运行
def test_backend_api():
    print("测试后端API是否正常运行...")
    
    # 测试数据服务状态API
    try:
        response = requests.get('http://localhost:8000/api/data/status')
        print(f'数据服务状态API响应: {response.status_code}')
        print(f'响应内容: {response.json()}')
    except Exception as e:
        print(f'数据服务状态API测试失败: {e}')
    
    # 测试获取交易日历API
    try:
        response = requests.get('http://localhost:8000/api/data/calendars')
        print(f'获取交易日历API响应: {response.status_code}')
        print(f'响应内容: {response.json()}')
    except Exception as e:
        print(f'获取交易日历API测试失败: {e}')
    
    # 测试获取成分股API
    try:
        response = requests.get('http://localhost:8000/api/data/instruments')
        print(f'获取成分股API响应: {response.status_code}')
        print(f'响应内容: {response.json()}')
    except Exception as e:
        print(f'获取成分股API测试失败: {e}')
    
    # 测试获取特征API
    try:
        response = requests.get('http://localhost:8000/api/data/features')
        print(f'获取特征API响应: {response.status_code}')
        print(f'响应内容: {response.json()}')
    except Exception as e:
        print(f'获取特征API测试失败: {e}')
    
    print("后端API测试完成")

if __name__ == "__main__":
    test_backend_api()
