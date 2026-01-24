import requests
import json

# 测试创建敏感配置
def test_create_sensitive_config():
    url = "http://localhost:8000/api/config/"
    headers = {"Content-Type": "application/json"}
    data = {
        "key": "test_sensitive_config",
        "value": "secret_value",
        "description": "测试敏感配置",
        "is_sensitive": True
    }
    response = requests.post(url, headers=headers, data=json.dumps(data))
    print("创建敏感配置响应:", response.status_code, response.json())
    return response.json()

# 测试获取敏感配置
def test_get_sensitive_config():
    url = "http://localhost:8000/api/config/test_sensitive_config"
    response = requests.get(url)
    print("获取敏感配置响应:", response.status_code, response.json())
    return response.json()

# 测试获取所有配置
def test_get_all_configs():
    url = "http://localhost:8000/api/config/"
    response = requests.get(url)
    print("获取所有配置响应:", response.status_code)
    print("配置数量:", len(response.json().get("data", {})))
    if "test_sensitive_config" in response.json().get("data", {}):
        print("敏感配置值:", response.json()["data"]["test_sensitive_config"])
    return response.json()

# 测试创建非敏感配置
def test_create_non_sensitive_config():
    url = "http://localhost:8000/api/config/"
    headers = {"Content-Type": "application/json"}
    data = {
        "key": "test_non_sensitive_config",
        "value": "public_value",
        "description": "测试非敏感配置",
        "is_sensitive": False
    }
    response = requests.post(url, headers=headers, data=json.dumps(data))
    print("创建非敏感配置响应:", response.status_code, response.json())
    return response.json()

# 测试获取非敏感配置
def test_get_non_sensitive_config():
    url = "http://localhost:8000/api/config/test_non_sensitive_config"
    response = requests.get(url)
    print("获取非敏感配置响应:", response.status_code, response.json())
    return response.json()

if __name__ == "__main__":
    print("测试开始...")
    test_create_sensitive_config()
    test_get_sensitive_config()
    test_get_all_configs()
    test_create_non_sensitive_config()
    test_get_non_sensitive_config()
    test_get_all_configs()
    print("测试结束...")