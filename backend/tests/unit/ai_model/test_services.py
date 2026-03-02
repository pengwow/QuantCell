"""
AI模型配置服务层单元测试

测试AIModelService和厂商适配器功能
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from ai_model.services import (
    AIModelService,
    OpenAIAdapter,
    AnthropicAdapter,
    DeepSeekAdapter,
)


class TestOpenAIAdapter:
    """OpenAI适配器单元测试类"""

    @pytest.mark.asyncio
    async def test_check_availability_success(self):
        """测试OpenAI服务可用性检查成功"""
        adapter = OpenAIAdapter("sk-test123")
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": [{"id": "gpt-4"}, {"id": "gpt-3.5-turbo"}]}
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.get.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            
            result = await adapter.check_availability()
        
        assert result["available"] is True
        assert "OpenAI服务可用" in result["message"]
        assert result["models_count"] == 2

    @pytest.mark.asyncio
    async def test_check_availability_unauthorized(self):
        """测试OpenAI服务可用性检查-密钥无效"""
        adapter = OpenAIAdapter("sk-invalid")
        
        mock_response = MagicMock()
        mock_response.status_code = 401
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.get.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            
            result = await adapter.check_availability()
        
        assert result["available"] is False
        assert "API密钥无效" in result["message"]

    @pytest.mark.asyncio
    async def test_check_availability_timeout(self):
        """测试OpenAI服务可用性检查-超时"""
        adapter = OpenAIAdapter("sk-test123")
        
        import httpx
        with patch("httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.get.side_effect = httpx.TimeoutException("Timeout")
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            
            result = await adapter.check_availability()
        
        assert result["available"] is False
        assert "超时" in result["message"]

    @pytest.mark.asyncio
    async def test_fetch_models(self):
        """测试获取OpenAI模型列表"""
        adapter = OpenAIAdapter("sk-test123")
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {"id": "gpt-4"},
                {"id": "gpt-4-turbo"},
                {"id": "gpt-3.5-turbo"},
                {"id": "text-embedding-ada-002"},  # 应该被过滤掉
            ]
        }
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.get.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            
            result = await adapter.fetch_models()
        
        assert len(result) == 3  # text-embedding-ada-002 被过滤
        assert all("gpt" in model["id"] for model in result)

    def test_get_model_description(self):
        """测试获取模型描述"""
        adapter = OpenAIAdapter("sk-test123")
        
        assert "GPT-4" in adapter._get_model_description("gpt-4")
        assert "GPT-3.5" in adapter._get_model_description("gpt-3.5-turbo")
        assert "OpenAI模型" == adapter._get_model_description("unknown-model")


class TestAnthropicAdapter:
    """Anthropic适配器单元测试类"""

    @pytest.mark.asyncio
    async def test_check_availability_success(self):
        """测试Anthropic服务可用性检查成功"""
        adapter = AnthropicAdapter("sk-ant-test123")
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": [{"id": "claude-3-opus"}, {"id": "claude-3-sonnet"}]}
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.get.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            
            result = await adapter.check_availability()
        
        assert result["available"] is True
        assert "Anthropic服务可用" in result["message"]

    def test_get_model_description(self):
        """测试获取模型描述"""
        adapter = AnthropicAdapter("sk-ant-test123")
        
        assert "Opus" in adapter._get_model_description("claude-3-opus")
        assert "Sonnet" in adapter._get_model_description("claude-3-sonnet")
        assert "Anthropic Claude模型" == adapter._get_model_description("unknown-model")


class TestDeepSeekAdapter:
    """DeepSeek适配器单元测试类"""

    @pytest.mark.asyncio
    async def test_check_availability_success(self):
        """测试DeepSeek服务可用性检查成功"""
        adapter = DeepSeekAdapter("sk-test123")
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": [{"id": "deepseek-chat"}, {"id": "deepseek-coder"}]}
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.get.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            
            result = await adapter.check_availability()
        
        assert result["available"] is True
        assert "DeepSeek服务可用" in result["message"]

    def test_get_model_description(self):
        """测试获取模型描述"""
        adapter = DeepSeekAdapter("sk-test123")
        
        assert "Chat" in adapter._get_model_description("deepseek-chat")
        assert "Coder" in adapter._get_model_description("deepseek-coder")
        assert "DeepSeek模型" == adapter._get_model_description("unknown-model")


class TestAIModelService:
    """AIModelService单元测试类"""

    def test_get_adapter_openai(self):
        """测试获取OpenAI适配器"""
        adapter = AIModelService.get_adapter("openai", "sk-test123")
        assert isinstance(adapter, OpenAIAdapter)

    def test_get_adapter_anthropic(self):
        """测试获取Anthropic适配器"""
        adapter = AIModelService.get_adapter("anthropic", "sk-test123")
        assert isinstance(adapter, AnthropicAdapter)

    def test_get_adapter_deepseek(self):
        """测试获取DeepSeek适配器"""
        adapter = AIModelService.get_adapter("deepseek", "sk-test123")
        assert isinstance(adapter, DeepSeekAdapter)

    def test_get_adapter_unsupported(self):
        """测试获取不支持的适配器"""
        adapter = AIModelService.get_adapter("unsupported", "sk-test123")
        assert adapter is None

    def test_get_adapter_case_insensitive(self):
        """测试适配器名称大小写不敏感"""
        adapter = AIModelService.get_adapter("OPENAI", "sk-test123")
        assert isinstance(adapter, OpenAIAdapter)

    @pytest.mark.asyncio
    async def test_check_provider_availability_success(self):
        """测试检查厂商可用性成功"""
        with patch.object(AIModelService, 'get_adapter') as mock_get_adapter:
            mock_adapter = AsyncMock()
            mock_adapter.check_availability.return_value = {
                "available": True,
                "message": "服务可用",
            }
            mock_adapter.fetch_models.return_value = [{"id": "gpt-4"}]
            mock_get_adapter.return_value = mock_adapter
            
            result = await AIModelService.check_provider_availability("openai", "sk-test123")
        
        assert result["available"] is True
        assert "models" in result

    @pytest.mark.asyncio
    async def test_check_provider_availability_unsupported(self):
        """测试检查不支持的厂商"""
        with patch.object(AIModelService, 'get_adapter', return_value=None):
            result = await AIModelService.check_provider_availability("unsupported", "sk-test123")
        
        assert result["available"] is False
        assert "不支持的厂商" in result["message"]
        assert "supported_providers" in result

    @pytest.mark.asyncio
    async def test_fetch_available_models(self):
        """测试获取可用模型列表"""
        with patch.object(AIModelService, 'get_adapter') as mock_get_adapter:
            mock_adapter = AsyncMock()
            mock_adapter.fetch_models.return_value = [{"id": "gpt-4"}, {"id": "gpt-3.5-turbo"}]
            mock_get_adapter.return_value = mock_adapter
            
            result = await AIModelService.fetch_available_models("openai", "sk-test123")
        
        assert len(result) == 2

    def test_get_supported_providers(self):
        """测试获取支持的厂商列表"""
        providers = AIModelService.get_supported_providers()
        
        assert len(providers) == 3
        assert any(p["id"] == "openai" for p in providers)
        assert any(p["id"] == "anthropic" for p in providers)
        assert any(p["id"] == "deepseek" for p in providers)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
