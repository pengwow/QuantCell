"""
AI模型配置接口测试

测试 /api/ai-models 相关的所有接口

作者: QuantCell Team
版本: 1.0.0
日期: 2026-03-08
"""

import json
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

# 导入应用
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from main import app
from settings.models import SystemConfigBusiness


# 创建测试客户端
client = TestClient(app)


# 模拟 JWT 认证
def mock_jwt_token():
    """生成测试用的 JWT token"""
    from utils.jwt_utils import create_jwt_token
    return create_jwt_token(
        data={"sub": "test_user", "name": "Test User"},
        expires_delta=None,
        refresh=False
    )


@pytest.fixture
def auth_headers():
    """提供认证请求头"""
    token = mock_jwt_token()
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def sample_model_config():
    """提供示例模型配置"""
    return {
        "provider": "openai",
        "name": "GPT-4 Test",
        "api_key": "sk-test-key",
        "api_host": "https://api.openai.com",
        "models": ["gpt-4", "gpt-3.5-turbo"],
        "is_default": False,
        "is_enabled": True,
        "proxy_enabled": False,
        "proxy_url": "",
        "proxy_username": "",
        "proxy_password": ""
    }


class TestAIModelAPI:
    """AI模型配置接口测试类"""
    
    def test_get_ai_models_empty(self, auth_headers):
        """测试获取空的AI模型列表"""
        with patch.object(SystemConfigBusiness, 'get_all_with_details', return_value={}):
            response = client.get("/api/ai-models/", headers=auth_headers)
            
            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert data["data"]["items"] == []
            assert data["data"]["total"] == 0
    
    def test_get_ai_models_with_data(self, auth_headers):
        """测试获取有数据的AI模型列表"""
        mock_configs = {
            "openai_abc123": {
                "key": "openai_abc123",
                "value": json.dumps({
                    "provider": "openai",
                    "name": "GPT-4",
                    "api_key": "sk-test",
                    "models": ["gpt-4"],
                    "is_enabled": True
                }),
                "name": "ai_models",
                "description": "GPT-4配置"
            }
        }
        
        with patch.object(SystemConfigBusiness, 'get_all_with_details', return_value=mock_configs):
            response = client.get("/api/ai-models/", headers=auth_headers)
            
            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert len(data["data"]["items"]) == 1
            assert data["data"]["items"][0]["provider"] == "openai"
    
    def test_create_ai_model(self, auth_headers, sample_model_config):
        """测试创建AI模型配置"""
        with patch.object(SystemConfigBusiness, 'set', return_value=True):
            response = client.post(
                "/api/ai-models/",
                headers=auth_headers,
                json=sample_model_config
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert data["data"]["provider"] == "openai"
            assert "id" in data["data"]
    
    def test_create_ai_model_failure(self, auth_headers, sample_model_config):
        """测试创建AI模型配置失败"""
        with patch.object(SystemConfigBusiness, 'set', return_value=False):
            response = client.post(
                "/api/ai-models/",
                headers=auth_headers,
                json=sample_model_config
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 1
            assert "失败" in data["message"]
    
    def test_get_ai_model_by_id(self, auth_headers):
        """测试获取单个AI模型配置"""
        model_id = "openai_abc123"
        mock_configs = {
            "openai_abc123": {
                "key": "openai_abc123",
                "value": json.dumps({
                    "id": "openai_abc123",
                    "provider": "openai",
                    "name": "GPT-4",
                    "api_key": "sk-test",
                    "models": ["gpt-4"],
                    "is_enabled": True
                }),
                "name": "ai_models",
                "description": "GPT-4配置"
            }
        }
        
        with patch.object(SystemConfigBusiness, 'get_all_with_details', return_value=mock_configs):
            response = client.get(f"/api/ai-models/{model_id}", headers=auth_headers)
            
            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert data["data"]["id"] == model_id
    
    def test_get_ai_model_not_found(self, auth_headers):
        """测试获取不存在的AI模型配置"""
        with patch.object(SystemConfigBusiness, 'get_all_with_details', return_value={}):
            response = client.get("/api/ai-models/nonexistent", headers=auth_headers)
            
            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 1
            assert "不存在" in data["message"]
    
    def test_update_ai_model(self, auth_headers):
        """测试更新AI模型配置"""
        model_id = "openai_abc123"
        mock_configs = {
            "openai_abc123": {
                "key": "openai_abc123",
                "value": json.dumps({
                    "id": "openai_abc123",
                    "provider": "openai",
                    "name": "GPT-4",
                    "api_key": "sk-test",
                    "models": ["gpt-4"],
                    "is_enabled": True
                }),
                "name": "ai_models"
            }
        }
        update_data = {
            "name": "GPT-4 Updated",
            "api_key": "sk-new-key"
        }
        
        with patch.object(SystemConfigBusiness, 'get_all_with_details', return_value=mock_configs):
            with patch.object(SystemConfigBusiness, 'set', return_value=True):
                response = client.put(
                    f"/api/ai-models/{model_id}",
                    headers=auth_headers,
                    json=update_data
                )
                
                assert response.status_code == 200
                data = response.json()
                assert data["code"] == 0
    
    def test_update_ai_model_not_found(self, auth_headers):
        """测试更新不存在的AI模型配置"""
        with patch.object(SystemConfigBusiness, 'get_all_with_details', return_value={}):
            response = client.put(
                "/api/ai-models/nonexistent",
                headers=auth_headers,
                json={"name": "Test"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 1
            assert "不存在" in data["message"]
    
    def test_delete_ai_model(self, auth_headers):
        """测试删除AI模型配置"""
        model_id = "openai_abc123"
        
        with patch.object(SystemConfigBusiness, 'set', return_value=True):
            response = client.delete(f"/api/ai-models/{model_id}", headers=auth_headers)
            
            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert data["data"]["id"] == model_id
    
    def test_get_supported_providers(self, auth_headers):
        """测试获取支持的AI厂商列表"""
        response = client.get("/api/ai-models/providers", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert "providers" in data["data"]
    
    def test_get_ai_models_with_filter(self, auth_headers):
        """测试带筛选条件获取AI模型列表"""
        mock_configs = {
            "openai_abc123": {
                "key": "openai_abc123",
                "value": json.dumps({
                    "provider": "openai",
                    "name": "GPT-4",
                    "is_enabled": True
                }),
                "name": "ai_models"
            },
            "anthropic_def456": {
                "key": "anthropic_def456",
                "value": json.dumps({
                    "provider": "anthropic",
                    "name": "Claude",
                    "is_enabled": False
                }),
                "name": "ai_models"
            }
        }
        
        with patch.object(SystemConfigBusiness, 'get_all_with_details', return_value=mock_configs):
            # 按 provider 筛选
            response = client.get(
                "/api/ai-models/?provider=openai",
                headers=auth_headers
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert len(data["data"]["items"]) == 1
            assert data["data"]["items"][0]["provider"] == "openai"
    
    def test_get_ai_models_pagination(self, auth_headers):
        """测试AI模型列表分页"""
        mock_configs = {}
        for i in range(15):
            mock_configs[f"openai_{i}"] = {
                "key": f"openai_{i}",
                "value": json.dumps({
                    "provider": "openai",
                    "name": f"Model {i}",
                    "is_enabled": True
                }),
                "name": "ai_models"
            }
        
        with patch.object(SystemConfigBusiness, 'get_all_with_details', return_value=mock_configs):
            response = client.get("/api/ai-models/?page=1&limit=10", headers=auth_headers)
            
            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert len(data["data"]["items"]) == 10
            assert data["data"]["total"] == 15
            assert data["data"]["page"] == 1
            assert data["data"]["limit"] == 10


class TestAIModelErrorHandling:
    """AI模型接口错误处理测试类"""
    
    def test_get_ai_models_config_not_dict(self, auth_headers):
        """测试 get_all_with_details 返回非字典类型"""
        with patch.object(SystemConfigBusiness, 'get_all_with_details', return_value=[]):
            response = client.get("/api/ai-models/", headers=auth_headers)
            
            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert data["data"]["items"] == []
    
    def test_get_ai_models_invalid_json(self, auth_headers):
        """测试配置值为无效JSON"""
        mock_configs = {
            "openai_abc123": {
                "key": "openai_abc123",
                "value": "invalid json",
                "name": "ai_models"
            }
        }
        
        with patch.object(SystemConfigBusiness, 'get_all_with_details', return_value=mock_configs):
            response = client.get("/api/ai-models/", headers=auth_headers)
            
            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert data["data"]["items"] == []
    
    def test_get_ai_models_empty_value(self, auth_headers):
        """测试配置值为空字符串"""
        mock_configs = {
            "openai_abc123": {
                "key": "openai_abc123",
                "value": "",
                "name": "ai_models"
            }
        }
        
        with patch.object(SystemConfigBusiness, 'get_all_with_details', return_value=mock_configs):
            response = client.get("/api/ai-models/", headers=auth_headers)
            
            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert data["data"]["items"] == []
    
    def test_unauthorized_access(self):
        """测试未授权访问"""
        response = client.get("/api/ai-models/")
        
        assert response.status_code == 401


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
