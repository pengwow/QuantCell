import os
import sys

import pytest
from fastapi.testclient import TestClient

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app

# 创建测试客户端
client = TestClient(app)


def test_read_root():
    """测试根路径的处理函数
    
    测试GET / 接口是否正常返回预期的响应
    
    预期结果：
        - 状态码为200
        - 返回的JSON数据包含{"Hello": "World"}
    """
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"Hello": "World"}


def test_read_item():
    """测试获取指定item_id的项目信息
    
    测试GET /items/{item_id} 接口是否正常返回预期的响应
    
    预期结果：
        - 状态码为200
        - 返回的JSON数据包含正确的item_id和查询参数
    """
    # 测试带查询参数的情况
    response = client.get("/items/123?q=test_query")
    assert response.status_code == 200
    assert response.json() == {"item_id": 123, "q": "test_query"}
    
    # 测试不带查询参数的情况
    response = client.get("/items/456")
    assert response.status_code == 200
    assert response.json() == {"item_id": 456, "q": None}


def test_get_data_service_status():
    """测试获取数据服务状态API
    
    测试GET /api/data/status 接口是否正常返回预期的响应
    
    预期结果：
        - 状态码为200
        - 返回的JSON数据包含正确的状态信息
    """
    response = client.get("/api/data/status")
    assert response.status_code == 200
    
    # 验证响应数据结构
    response_data = response.json()
    assert response_data["code"] == 0
    assert response_data["message"] == "获取数据服务状态成功"
    assert response_data["data"]["status"] == "running"


def test_read_item_invalid_id():
    """测试使用无效的item_id访问接口
    
    测试GET /items/{item_id} 接口在传入无效ID时的处理
    
    预期结果：
        - 状态码为422（请求验证错误）
    """
    response = client.get("/items/invalid_id")
    # 预期返回422，因为item_id应该是整数类型
    assert response.status_code == 422
