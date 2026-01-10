import requests
import json

# 测试解析策略脚本API
def test_parse_strategy():
    url = "http://localhost:8000/api/strategy/parse"
    headers = {"Content-Type": "application/json"}
    data = {
        "strategy_name": "test_strategy",
        "file_content": "class TestStrategy(Strategy):\n    \"\"\"\n    这是一个测试策略\n    \"\"\"\n    \n    def __init__(self, params):\n        self.params = params\n    \n    def next(self):\n        self.buy()"
    }
    
    try:
        response = requests.post(url, headers=headers, data=json.dumps(data))
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        return response.json()
    except Exception as e:
        print(f"Error: {e}")
        return None

if __name__ == "__main__":
    test_parse_strategy()