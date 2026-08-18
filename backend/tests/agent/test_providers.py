"""LLM提供者测试 - OpenAIProvider"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from agent.providers.base import LLMProvider, LLMResponse, StreamChunk, StreamEvent
from agent.providers.openai_provider import OpenAIProvider


class TestLLMResponse:
    """测试 LLMResponse 数据结构"""

    def test_llm_response_creation(self):
        """测试创建LLM响应"""
        response = LLMResponse(
            content="Hello!",
            has_tool_calls=False,
            tool_calls=[],
        )

        assert response.content == "Hello!"
        assert response.has_tool_calls is False
        assert response.tool_calls == []
        assert response.finish_reason is None
        assert response.reasoning_content is None

    def test_llm_response_with_tool_calls(self):
        """测试带工具调用的响应"""
        tool_calls = [{"id": "call_1", "name": "read_file", "arguments": '{"path": "test.txt"}'}]
        response = LLMResponse(
            content=None,
            has_tool_calls=True,
            tool_calls=tool_calls,
            finish_reason="tool_calls",
        )

        assert response.content is None
        assert response.has_tool_calls is True
        assert len(response.tool_calls) == 1
        assert response.finish_reason == "tool_calls"

    def test_llm_response_with_reasoning(self):
        """测试带推理内容的响应"""
        response = LLMResponse(
            content="The answer is 4.",
            has_tool_calls=False,
            tool_calls=[],
            reasoning_content="Thinking: 2+2=4",
        )

        assert response.reasoning_content == "Thinking: 2+2=4"


class TestStreamChunk:
    """测试 StreamChunk 数据结构"""

    def test_stream_chunk_creation(self):
        """测试创建流式数据块"""
        chunk = StreamChunk(
            content="Hello",
            delta="Hello",
        )

        assert chunk.content == "Hello"
        assert chunk.delta == "Hello"
        assert chunk.finish_reason is None
        assert chunk.is_tool_call is False
        assert chunk.tool_calls is None

    def test_stream_chunk_with_tool_calls(self):
        """测试带工具调用的数据块"""
        tool_calls = [{"id": "call_1", "name": "read_file", "arguments": {}}]
        chunk = StreamChunk(
            content="",
            finish_reason="tool_calls",
            is_tool_call=True,
            tool_calls=tool_calls,
        )

        assert chunk.is_tool_call is True
        assert len(chunk.tool_calls) == 1
        assert chunk.finish_reason == "tool_calls"

    def test_stream_chunk_with_reasoning(self):
        """测试带推理内容的数据块"""
        chunk = StreamChunk(
            reasoning_content="Thinking...",
        )

        assert chunk.reasoning_content == "Thinking..."

    def test_stream_chunk_type(self):
        """测试数据块类型"""
        # 工具调用
        chunk1 = StreamChunk(is_tool_call=True)
        assert chunk1.chunk_type == "tool_call"

        # 完成
        chunk2 = StreamChunk(finish_reason="stop")
        assert chunk2.chunk_type == "done"

        # 推理
        chunk3 = StreamChunk(reasoning_content="thinking")
        assert chunk3.chunk_type == "reasoning"

        # 内容
        chunk4 = StreamChunk(delta="text")
        assert chunk4.chunk_type == "content"

        # 空
        chunk5 = StreamChunk()
        assert chunk5.chunk_type == "empty"


class TestStreamEvent:
    """测试 StreamEvent 数据结构"""

    def test_stream_event_creation(self):
        """测试创建流式事件"""
        event = StreamEvent(
            event_type="content",
            data={"content": "Hello"},
        )

        assert event.event_type == "content"
        assert event.data["content"] == "Hello"
        assert event.timestamp > 0

    def test_stream_event_types(self):
        """测试不同事件类型"""
        events = [
            StreamEvent(event_type="start", data={}),
            StreamEvent(event_type="content", data={}),
            StreamEvent(event_type="reasoning", data={}),
            StreamEvent(event_type="tool_calls", data={}),
            StreamEvent(event_type="tool_start", data={}),
            StreamEvent(event_type="tool_result", data={}),
            StreamEvent(event_type="complete", data={}),
            StreamEvent(event_type="error", data={}),
        ]

        assert len(events) == 8
        for event in events:
            assert event.event_type in [
                "start",
                "content",
                "reasoning",
                "tool_calls",
                "tool_start",
                "tool_result",
                "complete",
                "error",
            ]


class TestOpenAIProvider:
    """测试 OpenAIProvider"""

    @pytest.fixture
    def provider(self):
        return OpenAIProvider(api_key="test-key", base_url="https://api.test.com")

    def test_provider_initialization(self, provider):
        """测试提供者初始化"""
        assert provider.api_key == "test-key"
        assert provider.base_url == "https://api.test.com"

    def test_provider_initialization_defaults(self, monkeypatch):
        """测试默认初始化"""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)

        provider = OpenAIProvider()

        assert provider.api_key == ""
        assert provider.base_url is None

    def test_provider_initialization_env(self, monkeypatch):
        """测试环境变量初始化"""
        monkeypatch.setenv("OPENAI_API_KEY", "env-key")
        monkeypatch.setenv("OPENAI_BASE_URL", "https://env.test.com")

        provider = OpenAIProvider()

        assert provider.api_key == "env-key"
        assert provider.base_url == "https://env.test.com"

    def test_get_default_model(self, provider, monkeypatch):
        """测试获取默认模型"""
        monkeypatch.delenv("DEFAULT_MODEL", raising=False)

        model = provider.get_default_model()

        assert model == "gpt-4o-mini"

    def test_get_default_model_env(self, provider, monkeypatch):
        """测试从环境变量获取默认模型"""
        monkeypatch.setenv("DEFAULT_MODEL", "gpt-4")

        model = provider.get_default_model()

        assert model == "gpt-4"

    @pytest.mark.asyncio
    async def test_chat_success(self, provider):
        """测试成功聊天调用"""
        # Mock OpenAI client
        mock_message = MagicMock()
        mock_message.content = "Hello!"
        mock_message.tool_calls = None
        mock_message.reasoning_content = None

        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_choice.finish_reason = "stop"

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 10
        mock_usage.completion_tokens = 5
        mock_usage.total_tokens = 15

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        provider._client = mock_client

        messages = [{"role": "user", "content": "Hello"}]
        response = await provider.chat(messages=messages)

        assert response.content == "Hello!"
        assert response.has_tool_calls is False
        assert response.tool_calls == []
        assert response.finish_reason == "stop"

    @pytest.mark.asyncio
    async def test_chat_with_tools(self, provider):
        """测试带工具的聊天调用"""
        # Mock工具调用
        mock_tc = MagicMock()
        mock_tc.id = "call_1"
        mock_tc.function.name = "read_file"
        mock_tc.function.arguments = '{"path": "test.txt"}'

        mock_message = MagicMock()
        mock_message.content = None
        mock_message.tool_calls = [mock_tc]
        mock_message.reasoning_content = None

        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_choice.finish_reason = "tool_calls"

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        provider._client = mock_client

        messages = [{"role": "user", "content": "Read file"}]
        tools = [{"type": "function", "function": {"name": "read_file"}}]
        response = await provider.chat(messages=messages, tools=tools)

        assert response.content is None
        assert response.has_tool_calls is True
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0]["name"] == "read_file"

    @pytest.mark.asyncio
    async def test_chat_with_reasoning(self, provider):
        """测试带推理的聊天调用"""
        mock_message = MagicMock()
        mock_message.content = "The answer is 4."
        mock_message.tool_calls = None
        mock_message.reasoning_content = "Thinking: 2+2=4"

        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_choice.finish_reason = "stop"

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        provider._client = mock_client

        messages = [{"role": "user", "content": "What is 2+2?"}]
        response = await provider.chat(messages=messages)

        assert response.content == "The answer is 4."
        assert response.reasoning_content == "Thinking: 2+2=4"

    @pytest.mark.asyncio
    async def test_chat_error(self, provider):
        """测试聊天错误处理"""
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=Exception("API Error"))
        provider._client = mock_client

        messages = [{"role": "user", "content": "Hello"}]

        with pytest.raises(Exception) as exc_info:
            await provider.chat(messages=messages)

        assert "API Error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_chat_stream(self, provider):
        """测试流式聊天调用"""
        # Mock流式响应
        mock_chunk1 = MagicMock()
        mock_chunk1.choices = [MagicMock()]
        mock_chunk1.choices[0].delta.content = "Hello"
        mock_chunk1.choices[0].delta.reasoning_content = None
        mock_chunk1.choices[0].delta.tool_calls = None
        mock_chunk1.choices[0].finish_reason = None
        mock_chunk1.usage = None

        mock_chunk2 = MagicMock()
        mock_chunk2.choices = [MagicMock()]
        mock_chunk2.choices[0].delta.content = " World"
        mock_chunk2.choices[0].delta.reasoning_content = None
        mock_chunk2.choices[0].delta.tool_calls = None
        mock_chunk2.choices[0].finish_reason = "stop"
        mock_chunk2.usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)

        async def mock_stream():
            yield mock_chunk1
            yield mock_chunk2

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_stream())
        provider._client = mock_client

        messages = [{"role": "user", "content": "Hello"}]
        chunks = []
        async for chunk in provider.chat_stream(messages=messages):
            chunks.append(chunk)

        assert len(chunks) >= 2
        assert chunks[0].delta == "Hello"
        assert chunks[1].delta == " World"

    @pytest.mark.asyncio
    async def test_chat_stream_error(self, provider):
        """测试流式聊天错误处理"""
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=Exception("Stream Error"))
        provider._client = mock_client

        messages = [{"role": "user", "content": "Hello"}]

        with pytest.raises(Exception) as exc_info:
            async for _chunk in provider.chat_stream(messages=messages):
                pass

        assert "Stream Error" in str(exc_info.value)


class TestLLMProviderAbstract:
    """测试 LLMProvider 抽象基类"""

    def test_cannot_instantiate(self):
        """测试不能直接实例化抽象类"""
        with pytest.raises(TypeError):
            LLMProvider()

    def test_must_implement_methods(self):
        """测试必须实现抽象方法"""

        class IncompleteProvider(LLMProvider):
            pass

        with pytest.raises(TypeError):
            IncompleteProvider()

    def test_complete_implementation(self):
        """测试完整实现"""

        class CompleteProvider(LLMProvider):
            async def chat(self, **kwargs):
                return LLMResponse(content="test", has_tool_calls=False, tool_calls=[])

            async def chat_stream(self, **kwargs):
                yield StreamChunk(content="test", delta="test")

            def get_default_model(self):
                return "test-model"

        provider = CompleteProvider()
        assert provider.get_default_model() == "test-model"
