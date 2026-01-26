import requests
import datetime

# 测试创建配置项并检查返回的时间
def test_timezone_fix():
    # 创建配置项的URL
    create_url = "http://localhost:8000/api/config"
    
    # 创建测试配置项
    test_config = {
        "key": "test_timezone_config",
        "value": "test_value",
        "description": "测试时区修复",
        "plugin": None,
        "name": "测试配置",
        "is_sensitive": False
    }
    
    try:
        # 创建配置项
        create_response = requests.post(create_url, json=test_config)
        create_response.raise_for_status()
        print(f"创建配置项状态码: {create_response.status_code}")
        print(f"创建配置项响应: {create_response.json()}")
        
        # 获取刚创建的配置项，查看时间
        get_url = f"http://localhost:8000/api/config/test_timezone_config"
        get_response = requests.get(get_url)
        get_response.raise_for_status()
        
        config_data = get_response.json()
        print(f"获取配置项状态码: {get_response.status_code}")
        print(f"获取配置项响应: {config_data}")
        
        # 检查时间字段
        if 'data' in config_data and ('created_at' in config_data['data'] or 'updated_at' in config_data['data']):
            print("\n=== 时间验证结果 ===")
            if 'created_at' in config_data['data']:
                print(f"created_at: {config_data['data']['created_at']}")
            if 'updated_at' in config_data['data']:
                print(f"updated_at: {config_data['data']['updated_at']}")
            print(f"timestamp: {config_data['timestamp']}")
            print(f"当前本地时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
    except requests.exceptions.RequestException as e:
        print(f"API请求失败: {e}")

if __name__ == "__main__":
    test_timezone_fix()