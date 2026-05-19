"""
AI模型配置API集成测试

测试完整的API接口流程
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from main import app


@pytest.fixture
def client():
    """创建测试客户端"""
    return TestClient(app)


@pytest.fixture
def mock_auth():
    """模拟JWT认证"""
    with patch("utils.auth.decode_jwt_token") as mock_decode:
        mock_decode.return_value = {"sub": "test_user", "name": "Test User"}
        yield mock_decode


@pytest.fixture
def mock_should_refresh():
    """模拟不需要刷新token"""
    with patch("utils.auth.should_refresh_token") as mock_refresh:
        mock_refresh.return_value = False
        yield mock_refresh


class TestAIModelAPI:
    """AI模型配置API集成测试类"""

    def test_get_ai_models_list(self, client, mock_auth, mock_should_refresh):
        """测试获取AI模型配置列表"""
        mock_providers = [{
            "id": 1,
            "provider": "openai",
            "name": "OpenAI Config",
            "api_host": "https://api.openai.com",
            "models": ["gpt-4"],
            "is_default": True,
            "is_enabled": "gpt-4",
            "created_at": "2026-03-02 10:00:00",
            "updated_at": "2026-03-02 10:00:00",
            "api_key_masked": "sk-...1234"
        }]
        with patch('ai_model.routes.get_ai_models_from_config', return_value=mock_providers):
            response = client.get(
                "/api/ai-models/",
                headers={"Authorization": "Bearer test_token"}
            )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["total"] == 1
        assert len(data["data"]["items"]) == 1

    def test_create_ai_model(self, client, mock_auth, mock_should_refresh):
        """测试创建AI模型配置"""
        with patch('ai_model.routes.save_ai_model_to_config', return_value=True):
            response = client.post(
                "/api/ai-models/",
                headers={"Authorization": "Bearer test_token"},
                json={
                    "provider": "openai",
                    "name": "Test Config",
                    "api_key": "sk-test123456789",
                    "api_host": "https://api.openai.com",
                    "models": ["gpt-4"],
                    "is_default": False,
                    "is_enabled": "gpt-4"
                }
            )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["provider"] == "openai"

    def test_get_ai_model_by_id(self, client, mock_auth, mock_should_refresh):
        """测试获取单个AI模型配置"""
        mock_providers = [{
            "id": 1,
            "provider": "openai",
            "name": "Test Config",
            "api_host": "https://api.openai.com",
            "models": ["gpt-4"],
            "is_default": True,
            "is_enabled": "gpt-4",
            "created_at": "2026-03-02 10:00:00",
            "updated_at": "2026-03-02 10:00:00",
            "api_key_masked": "sk-...1234"
        }]
        with patch('ai_model.routes.get_ai_models_from_config', return_value=mock_providers):
            response = client.get(
                "/api/ai-models/1",
                headers={"Authorization": "Bearer test_token"}
            )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["id"] == 1

    def test_update_ai_model(self, client, mock_auth, mock_should_refresh):
        """测试更新AI模型配置"""
        mock_providers = [{
            "id": 1,
            "provider": "openai",
            "name": "Test Config",
            "api_host": "https://api.openai.com",
            "models": ["gpt-4"],
            "is_default": True,
            "is_enabled": "gpt-4",
            "created_at": "2026-03-02 10:00:00",
            "updated_at": "2026-03-02 10:00:00",
            "api_key_masked": "sk-...1234"
        }]
        with patch('ai_model.routes.get_ai_models_from_config', return_value=mock_providers), \
             patch('ai_model.routes.save_ai_model_to_config', return_value=True):
            response = client.put(
                "/api/ai-models/1",
                headers={"Authorization": "Bearer test_token"},
                json={
                    "name": "Updated Config",
                    "is_default": True
                }
            )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["name"] == "Updated Config"

    def test_delete_ai_model(self, client, mock_auth, mock_should_refresh):
        """测试删除AI模型配置"""
        with patch('ai_model.routes.delete_ai_model_from_config', return_value=True):
            response = client.delete(
                "/api/ai-models/1",
                headers={"Authorization": "Bearer test_token"}
            )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0

    def test_get_supported_providers(self, client, mock_auth, mock_should_refresh):
        """测试获取支持的厂商列表"""
        with patch("ai_model.services.AIModelService.get_supported_providers") as mock_get:
            mock_get.return_value = [
                {"id": "openai", "name": "OpenAI", "description": "OpenAI GPT系列模型"},
                {"id": "anthropic", "name": "Anthropic", "description": "Anthropic Claude系列模型"}
            ]

            response = client.get(
                "/api/ai-models/providers",
                headers={"Authorization": "Bearer test_token"}
            )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert len(data["data"]["providers"]) == 2

    def test_check_ai_model_availability(self, client, mock_auth, mock_should_refresh):
        """测试检查AI模型可用性"""
        with patch("ai_model.services.AIModelService.check_provider_availability") as mock_check:
            mock_check.return_value = {
                "available": True,
                "message": "OpenAI服务可用",
                "models": [
                    {"id": "gpt-4", "name": "gpt-4", "description": "GPT-4模型", "provider": "openai"}
                ]
            }

            response = client.post(
                "/api/ai-models/check",
                headers={"Authorization": "Bearer test_token"},
                json={
                    "provider": "openai",
                    "api_key": "sk-test123456789",
                    "api_host": "https://api.openai.com"
                }
            )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["available"] is True
        assert len(data["data"]["models"]) == 1

    def test_check_ai_model_availability_invalid_provider(self, client, mock_auth, mock_should_refresh):
        """测试检查无效厂商的模型可用性"""
        with patch("ai_model.services.AIModelService.check_provider_availability") as mock_check:
            mock_check.return_value = {
                "available": False,
                "message": "不支持的厂商: invalid_provider",
                "error": "Unsupported provider",
                "supported_providers": ["openai", "anthropic"]
            }

            response = client.post(
                "/api/ai-models/check",
                headers={"Authorization": "Bearer test_token"},
                json={
                    "provider": "invalid_provider",
                    "api_key": "sk-test123456789",
                    "api_host": "https://api.openai.com"
                }
            )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["available"] is False

    def test_get_available_models(self, client, mock_auth, mock_should_refresh):
        """测试获取配置的可用模型列表"""
        mock_providers = [{
            "id": 1,
            "provider": "openai",
            "name": "Test Config",
            "api_host": "https://api.openai.com",
            "api_key": "sk-test123456789",
            "is_default": True,
            "is_enabled": "gpt-4",
        }]
        mock_models = [
            {"id": "gpt-4", "name": "gpt-4", "description": "GPT-4模型", "provider": "openai"},
            {"id": "gpt-3.5-turbo", "name": "gpt-3.5-turbo", "description": "GPT-3.5 Turbo模型", "provider": "openai"}
        ]
        with patch('ai_model.routes.get_ai_models_from_config', return_value=mock_providers), \
             patch("ai_model.services.AIModelService.fetch_available_models", return_value=mock_models):
            response = client.get(
                "/api/ai-models/1/models",
                headers={"Authorization": "Bearer test_token"}
            )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["provider"] == "openai"
        assert data["data"]["total"] == 2
        assert len(data["data"]["models"]) == 2

    def test_get_available_models_config_not_found(self, client, mock_auth, mock_should_refresh):
        """测试获取不存在配置的可用模型列表"""
        with patch('ai_model.routes.get_ai_models_from_config', return_value=[]):
            response = client.get(
                "/api/ai-models/999/models",
                headers={"Authorization": "Bearer test_token"}
            )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 1
        assert "AI模型配置不存在" in data["message"]

    def test_get_available_models_no_api_key(self, client, mock_auth, mock_should_refresh):
        """测试获取没有API密钥的配置的可用模型列表"""
        mock_providers = [{
            "id": 1,
            "provider": "openai",
            "name": "Test Config",
            "api_host": "https://api.openai.com",
            "is_default": True,
        }]
        with patch('ai_model.routes.get_ai_models_from_config', return_value=mock_providers):
            response = client.get(
                "/api/ai-models/1/models",
                headers={"Authorization": "Bearer test_token"}
            )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 1
        assert "API密钥" in data["message"]


class TestAIModelAuth:
    """AI模型配置认证测试类"""

    def test_unauthorized_access(self, client):
        """测试未授权访问被拒绝"""
        response = client.get("/api/ai-models/")

        assert response.status_code == 401

    def test_invalid_token(self, client):
        """测试无效令牌"""
        with patch("utils.auth.decode_jwt_token") as mock_decode:
            from utils.jwt_utils import TokenInvalidError
            mock_decode.side_effect = TokenInvalidError("Invalid token")

            response = client.get(
                "/api/ai-models/",
                headers={"Authorization": "Bearer invalid_token"}
            )

        assert response.status_code == 401


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
