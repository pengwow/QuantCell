"""
AI模型配置服务层单元测试

测试AIModelService和厂商适配器功能
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_model.services import (
    AIModelService,
    AnthropicAdapter,
    DeepSeekAdapter,
    OpenAIAdapter,
)


class TestOpenAIAdapter:
    """OpenAI适配器单元测试类"""

    @pytest.mark.asyncio
    async def test_check_availability_success(self):
        """测试OpenAI服务可用性检查成功"""
        from ai_model.services import OpenAIAdapter

        mock_models_response = MagicMock()
        mock_models_response.data = [
            MagicMock(id="gpt-4o"),
            MagicMock(id="gpt-4o-mini"),
        ]

        mock_models = AsyncMock()
        mock_models.list.return_value = mock_models_response

        mock_client = AsyncMock()
        mock_client.models = mock_models

        with patch("ai_model.services.AsyncOpenAI", return_value=mock_client):
            adapter = OpenAIAdapter("sk-test123")
            result = await adapter.check_availability()

        assert result["available"] is True
        assert "OpenAI服务可用" in result["message"]

    @pytest.mark.asyncio
    async def test_check_availability_unauthorized(self):
        """测试OpenAI服务可用性检查-密钥无效"""
        from openai import AuthenticationError

        from ai_model.services import OpenAIAdapter

        mock_models = AsyncMock()
        mock_models.list.side_effect = AuthenticationError(
            "Invalid API key",
            response=MagicMock(status_code=401),
            body={"error": {"message": "Invalid API key"}},
        )

        mock_client = AsyncMock()
        mock_client.models = mock_models

        with patch("ai_model.services.AsyncOpenAI", return_value=mock_client):
            adapter = OpenAIAdapter("sk-invalid")
            result = await adapter.check_availability()

        assert result["available"] is False
        assert "API密钥无效" in result["message"]

    @pytest.mark.asyncio
    async def test_check_availability_timeout(self):
        """测试OpenAI服务可用性检查-超时"""
        from openai import APITimeoutError

        from ai_model.services import OpenAIAdapter

        mock_models = AsyncMock()
        mock_models.list.side_effect = APITimeoutError("Timeout")

        mock_client = AsyncMock()
        mock_client.models = mock_models

        with patch("ai_model.services.AsyncOpenAI", return_value=mock_client):
            adapter = OpenAIAdapter("sk-test123")
            result = await adapter.check_availability()

        assert result["available"] is False
        assert "超时" in result["message"]

    @pytest.mark.asyncio
    async def test_fetch_models(self):
        """测试获取OpenAI模型列表"""
        from ai_model.services import OpenAIAdapter

        mock_models = MagicMock()
        mock_models.data = [
            MagicMock(id="gpt-4"),
            MagicMock(id="gpt-4-turbo"),
            MagicMock(id="gpt-3.5-turbo"),
        ]

        mock_models_list = AsyncMock()
        mock_models_list.list.return_value = mock_models

        mock_client = AsyncMock()
        mock_client.models = mock_models_list

        with patch("ai_model.services.AsyncOpenAI", return_value=mock_client):
            adapter = OpenAIAdapter("sk-test123")
            result = await adapter.fetch_models()

        assert len(result) == 3
        assert all("gpt" in model["id"] for model in result)

    def test_get_model_description(self):
        """测试获取模型描述"""
        adapter = OpenAIAdapter("sk-test123")

        assert "GPT-4" in adapter._get_model_description("gpt-4")
        assert "GPT-3.5" in adapter._get_model_description("gpt-3.5-turbo")
        assert adapter._get_model_description("unknown-model") == "OpenAI模型"


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
        assert adapter._get_model_description("unknown-model") == "Anthropic Claude模型"


class TestDeepSeekAdapter:
    """DeepSeek适配器单元测试类"""

    @pytest.mark.asyncio
    async def test_check_availability_success(self):
        """测试DeepSeek服务可用性检查成功"""
        from ai_model.services import DeepSeekAdapter

        mock_models_response = MagicMock()
        mock_models_response.data = [
            MagicMock(id="deepseek-chat"),
            MagicMock(id="deepseek-coder"),
        ]

        mock_models = AsyncMock()
        mock_models.list.return_value = mock_models_response

        mock_client = AsyncMock()
        mock_client.models = mock_models

        with patch("ai_model.services.AsyncOpenAI", return_value=mock_client):
            adapter = DeepSeekAdapter("sk-test123")
            result = await adapter.check_availability()

        assert result["available"] is True
        assert "DeepSeek服务可用" in result["message"]

    def test_get_model_description(self):
        """测试获取模型描述"""
        adapter = DeepSeekAdapter("sk-test123")

        assert "Chat" in adapter._get_model_description("deepseek-chat")
        assert "Coder" in adapter._get_model_description("deepseek-coder")
        assert adapter._get_model_description("unknown-model") == "DeepSeek模型"


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
        with patch.object(AIModelService, "get_adapter") as mock_get_adapter:
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
        with patch.object(AIModelService, "get_adapter", return_value=None):
            result = await AIModelService.check_provider_availability("unsupported", "sk-test123")

        assert result["available"] is False
        assert "不支持的厂商" in result["message"]
        assert "supported_providers" in result

    @pytest.mark.asyncio
    async def test_fetch_available_models(self):
        """测试获取可用模型列表"""
        with patch.object(AIModelService, "get_adapter") as mock_get_adapter:
            mock_adapter = AsyncMock()
            mock_adapter.fetch_models.return_value = [
                {"id": "gpt-4"},
                {"id": "gpt-3.5-turbo"},
            ]
            mock_get_adapter.return_value = mock_adapter

            result = await AIModelService.fetch_available_models("openai", "sk-test123")

        assert len(result) == 2

    def test_get_supported_providers(self):
        """测试获取支持的厂商列表"""
        providers = AIModelService.get_supported_providers()

        assert len(providers) >= 3
        assert any(p["id"] == "openai" for p in providers)
        assert any(p["id"] == "anthropic" for p in providers)
        assert any(p["id"] == "deepseek" for p in providers)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
