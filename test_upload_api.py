import requests
import json

# 测试上传策略文件API
def test_upload_strategy():
    url = "http://localhost:8000/api/strategy/upload"
    headers = {"Content-Type": "application/json"}
    data = {
        "strategy_name": "test_upload_strategy",
        "file_content": "class TestUploadStrategy(Strategy):\n    \"\"\"\n    这是一个测试上传策略\n    \"\"\"\n    \n    def __init__(self, params):\n        self.params = params\n    \n    def next(self):\n        self.buy()"
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
    test_upload_strategy()