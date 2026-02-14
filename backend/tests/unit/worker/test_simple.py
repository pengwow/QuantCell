"""
简单测试 - 验证 mock 是否生效
"""

import sys
from unittest.mock import MagicMock, AsyncMock

# 在导入任何其他模块之前创建 mock
_mock_service = MagicMock()
_mock_service.start_worker_async = AsyncMock(return_value="task-123")

# 注入 mock
sys.modules['worker.service'] = _mock_service

from fastapi.testclient import TestClient
from main import app


def test_start_worker_not_found():
    """测试启动不存在的Worker"""
    with TestClient(app) as client:
        response = client.post("/api/workers/99999/lifecycle/start")
        
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")
        
        assert response.status_code == 404
