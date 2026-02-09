"""
集成测试全局Fixture配置

提供API测试所需的共享Fixture
"""

import pytest
from fastapi.testclient import TestClient
from typing import Generator, Dict, Any
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

# 添加backend目录到Python路径
backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from main import app


@pytest.fixture(scope="session")
def client() -> Generator[TestClient, None, None]:
    """
    创建TestClient实例
    
    在整个测试会话期间共享同一个TestClient实例
    
    Yields:
        TestClient: FastAPI测试客户端
    """
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="function")
def auth_headers() -> Dict[str, str]:
    """
    生成有效的认证请求头
    
    使用有效的JWT测试令牌进行认证
    
    Returns:
        Dict[str, str]: 包含Authorization头的字典
    """
    import jwt
    from utils.jwt_utils import JWT_SECRET_KEY, JWT_ALGORITHM
    
    # 创建一个有效的令牌（1小时后过期）
    token = jwt.encode(
        {
            "sub": "test_user_123",
            "name": "Test User",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            "iat": datetime.now(timezone.utc)
        },
        JWT_SECRET_KEY,
        algorithm=JWT_ALGORITHM
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="function")
def valid_auth_headers() -> Dict[str, str]:
    """
    生成有效的认证请求头（与auth_headers相同，用于兼容不同测试用例的命名习惯）
    
    使用有效的JWT测试令牌进行认证
    
    Returns:
        Dict[str, str]: 包含Authorization头的字典
    """
    import jwt
    from utils.jwt_utils import JWT_SECRET_KEY, JWT_ALGORITHM
    
    token = jwt.encode(
        {
            "sub": "test_user_123",
            "name": "Test User",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            "iat": datetime.now(timezone.utc)
        },
        JWT_SECRET_KEY,
        algorithm=JWT_ALGORITHM
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="function")
def invalid_auth_headers() -> Dict[str, str]:
    """
    生成无效认证请求头
    
    Returns:
        Dict[str, str]: 包含无效令牌的字典
    """
    return {"Authorization": "Bearer invalid_token"}


@pytest.fixture(scope="function")
def expired_auth_headers() -> Dict[str, str]:
    """
    生成过期令牌请求头
    
    使用正确的密钥创建真实的过期JWT令牌
    
    Returns:
        Dict[str, str]: 包含过期令牌的字典
    """
    import jwt
    from utils.jwt_utils import JWT_SECRET_KEY, JWT_ALGORITHM
    
    # 创建一个已过期的令牌（过期时间为1小时前）
    expired_token = jwt.encode(
        {
            "sub": "test_user_123",
            "name": "Test User",
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),  # 已过期
            "iat": datetime.now(timezone.utc) - timedelta(hours=2)
        },
        JWT_SECRET_KEY,
        algorithm=JWT_ALGORITHM
    )
    return {"Authorization": f"Bearer {expired_token}"}


@pytest.fixture(scope="function")
def malformed_auth_headers() -> Dict[str, str]:
    """
    生成格式错误的认证请求头
    
    Returns:
        Dict[str, str]: 包含格式错误Authorization头的字典
    """
    return {"Authorization": "InvalidFormat token"}


@pytest.fixture(scope="function")
def missing_auth_headers() -> Dict[str, str]:
    """
    生成缺少Bearer前缀的认证请求头
    
    Returns:
        Dict[str, str]: 包含格式错误Authorization头的字典
    """
    return {"Authorization": "token_without_bearer"}


@pytest.fixture(scope="function")
def empty_auth_headers() -> Dict[str, str]:
    """
    生成空Authorization头的请求头
    
    Returns:
        Dict[str, str]: 包含空Authorization头的字典
    """
    return {"Authorization": ""}


@pytest.fixture(scope="function")
def valid_strategy_data() -> Dict[str, Any]:
    """
    生成有效的策略数据
    
    Returns:
        Dict[str, Any]: 策略数据字典
    """
    return {
        "strategy_name": "test_strategy",
        "file_content": (
            "class TestStrategy(Strategy):\n"
            "    '''测试策略'''\n"
            "    def next(self):\n"
            "        if self.data.close > self.data.open:\n"
            "            self.buy()\n"
            "        else:\n"
            "            self.sell()\n"
        ),
        "version": "1.0.0",
        "description": "这是一个测试策略",
        "tags": ["test", "demo"]
    }


@pytest.fixture(scope="function")
def valid_backtest_config() -> Dict[str, Any]:
    """
    生成有效的回测配置数据
    
    Returns:
        Dict[str, Any]: 回测配置字典
    """
    return {
        "strategy_config": {
            "strategy_name": "sma_cross",
            "params": {
                "n1": 10,
                "n2": 20
            }
        },
        "backtest_config": {
            "symbol": "BTCUSDT",
            "interval": "1h",
            "start_date": "2023-01-01",
            "end_date": "2023-12-31",
            "initial_capital": 100000.0,
            "commission": 0.001,
            "slippage": 0.001
        }
    }


@pytest.fixture(scope="function")
def valid_config_data() -> Dict[str, Any]:
    """
    生成有效的配置数据
    
    Returns:
        Dict[str, Any]: 配置数据字典
    """
    return {
        "key": "test_config_key",
        "value": "test_config_value",
        "description": "测试配置项",
        "plugin": None,
        "name": "测试配置",
        "is_sensitive": False
    }


@pytest.fixture(scope="function")
def api_base_url() -> str:
    """
    API基础URL
    
    Returns:
        str: API基础路径
    """
    return "/api"


@pytest.fixture(scope="function")
def assert_api_response():
    """
    API响应断言辅助函数
    
    Returns:
        function: 断言函数
    """
    def _assert(response, expected_code: int = 0, expected_status: int = 200):
        """
        断言API响应
        
        Args:
            response: HTTP响应对象
            expected_code: 期望的业务状态码
            expected_status: 期望的HTTP状态码
        """
        assert response.status_code == expected_status, (
            f"期望状态码 {expected_status}, 实际 {response.status_code}, "
            f"响应内容: {response.text}"
        )
        
        if expected_status == 200:
            data = response.json()
            assert "code" in data, f"响应缺少code字段: {data}"
            assert data["code"] == expected_code, (
                f"期望业务码 {expected_code}, 实际 {data['code']}, "
                f"消息: {data.get('message', 'N/A')}"
            )
    
    return _assert


@pytest.fixture(scope="function")
def assert_error_response():
    """
    错误响应断言辅助函数
    
    Returns:
        function: 断言函数
    """
    def _assert(response, expected_status: int, expected_error_contains: str = None):
        """
        断言错误响应
        
        Args:
            response: HTTP响应对象
            expected_status: 期望的HTTP状态码
            expected_error_contains: 期望错误消息包含的文本
        """
        assert response.status_code == expected_status, (
            f"期望状态码 {expected_status}, 实际 {response.status_code}"
        )
        
        data = response.json()
        assert "detail" in data, f"错误响应缺少detail字段: {data}"
        
        if expected_error_contains:
            detail_str = str(data["detail"])
            assert expected_error_contains in detail_str, (
                f"期望错误消息包含 '{expected_error_contains}', "
                f"实际: {detail_str}"
            )
    
    return _assert
